"""
title: AI-Carmine Vulkan Controller
version: 2.0.0

OpenWebUI Pipe that acts as a controller, not as a raw proxy:
1. asks an OpenWebUI-served model to produce a bounded structured plan;
2. executes one or more dynamic calls against the Vulkan bridge public endpoint;
3. asks the OpenWebUI model to synthesize the terminal answer from bridge evidence.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Optional

from pydantic import BaseModel, Field


EventEmitter = Optional[Callable[[dict[str, Any]], Any]]


class Pipe:
    class Valves(BaseModel):
        PIPELINE_ID: str = Field(default="aicarmine-vulkan-controller")
        PIPELINE_NAME: str = Field(default="AI-Carmine Vulkan Controller")

        OPENWEBUI_BASE_URL: str = Field(default="http://open-webui:8080")
        OPENWEBUI_API_KEY: str = Field(default="")
        PLANNER_MODEL: str = Field(default="gpt-oss:latest")
        SYNTH_MODEL: str = Field(default="gpt-oss:latest")

        VULKAN_BRIDGE_URL: str = Field(default="http://host.docker.internal:3571/vulkan_helper")
        BRIDGE_TIMEOUT_SECONDS: int = Field(default=1200, ge=15, le=3600)
        BRIDGE_WAIT_SECONDS: int = Field(default=900, ge=1, le=1800)
        MAX_BRIDGE_CALLS: int = Field(default=3, ge=1, le=8)
        DEFAULT_APPROVAL_MODE: str = Field(default="safe_write_lab")
        DEFAULT_RETURN_MODE: str = Field(default="wait")

        PLANNER_TIMEOUT_SECONDS: int = Field(default=120, ge=15, le=600)
        SYNTH_TIMEOUT_SECONDS: int = Field(default=180, ge=15, le=600)
        MODEL_TEMPERATURE: float = Field(default=0.0, ge=0.0, le=1.0)
        MAX_OBSERVATION_CHARS: int = Field(default=70000, ge=4000, le=250000)
        MAX_FINAL_CONTEXT_CHARS: int = Field(default=90000, ge=4000, le=250000)
        DEBUG_RETURN_RAW_PLAN: bool = Field(default=False)

    def __init__(self) -> None:
        self.valves = self.Valves()

    def pipes(self) -> list[dict[str, str]]:
        return [{"id": self.valves.PIPELINE_ID, "name": self.valves.PIPELINE_NAME}]

    async def pipe(
        self,
        body: dict[str, Any],
        __user__: Optional[dict[str, Any]] = None,
        __event_emitter__: EventEmitter = None,
        __request__: Any = None,
    ) -> str:
        user_request = self._last_user_message(body)
        if not user_request:
            return self._sectioned_error(
                symptom="OpenWebUI ha chiamato la Pipeline senza un messaggio utente leggibile.",
                evidence=f"body keys={sorted(body.keys())}",
                cause="Formato body inatteso o history vuota.",
                fix="Inviare una richiesta testuale oppure verificare il payload OpenWebUI.",
            )

        await self._emit(__event_emitter__, "status", "Planner OpenWebUI: strutturazione richiesta", False)
        plan = self._build_plan(user_request=user_request, body=body, user=__user__)
        calls = self._normalize_calls(plan, user_request)
        if not calls:
            return self._sectioned_error(
                symptom="Il planner non ha prodotto step eseguibili.",
                evidence=json.dumps(plan, ensure_ascii=False, indent=2)[:6000],
                cause="Output planner non conforme allo schema o richiesta senza lavoro operativo.",
                fix="Correggere prompt/schema planner o forzare almeno una chiamata bridge.",
            )

        observations: list[dict[str, Any]] = []
        for index, call in enumerate(calls, start=1):
            await self._emit(
                __event_emitter__,
                "status",
                f"Vulkan bridge: step {index}/{len(calls)}",
                False,
            )
            observations.append(self._call_bridge(call, index=index, total=len(calls)))

        await self._emit(__event_emitter__, "status", "Sintesi finale con modello OpenWebUI", False)
        final_answer = self._synthesize(user_request=user_request, plan=plan, observations=observations)
        await self._emit(__event_emitter__, "status", "Completato", True)

        if self.valves.DEBUG_RETURN_RAW_PLAN:
            return (
                final_answer.rstrip()
                + "\n\n---\n\n```json\n"
                + json.dumps({"plan": plan, "observations": observations}, ensure_ascii=False, indent=2)[:20000]
                + "\n```"
            )
        return final_answer

    def _last_user_message(self, body: dict[str, Any]) -> str:
        messages = body.get("messages") or []
        if isinstance(messages, list):
            for message in reversed(messages):
                if not isinstance(message, dict):
                    continue
                if message.get("role") == "user":
                    content = message.get("content")
                    if isinstance(content, str) and content.strip():
                        return content.strip()
                    if isinstance(content, list):
                        chunks: list[str] = []
                        for item in content:
                            if isinstance(item, dict) and isinstance(item.get("text"), str):
                                chunks.append(item["text"])
                        text = "\n".join(chunks).strip()
                        if text:
                            return text
        prompt = body.get("prompt") or body.get("query") or body.get("request")
        return str(prompt or "").strip()

    def _build_plan(self, user_request: str, body: dict[str, Any], user: Optional[dict[str, Any]]) -> dict[str, Any]:
        system = """
Sei il planner esterno di una OpenWebUI Pipeline per coding/repo work.
Devi produrre SOLO JSON valido.
La Pipeline NON deve essere un proxy: deve decomporre la richiesta in step operativi minimi e verificabili.
Il layer operativo reale e dinamico e' il Vulkan bridge: ogni step bridge deve passare una richiesta semantica completa a /vulkan_helper; il bridge inoltra al planner interno 3572 e usera' vulkan_helper/strumenti interni quando serve.
Non inventare risultati. Non proporre wrapper se basta una chiamata bridge.
Schema obbligatorio:
{
  "intent": "coding|repo_analysis|debug|patch|status|general",
  "needs_bridge": true,
  "risk": "read_only|safe_write_lab|requires_user_consent",
  "rationale": "breve",
  "calls": [
    {
      "title": "breve titolo",
      "request": "richiesta completa da inviare al bridge",
      "function": "vulkan_helper|repo_status|repo_search|repo_read|repo_command|repo_capabilities|",
      "approval_mode": "read_only|safe_write_lab|requires_user_consent",
      "return_mode": "wait",
      "wait_seconds": 900
    }
  ],
  "final_answer_policy": "Usa solo evidenze ritornate dal bridge; separa sintomo, evidenza, causa, fix, verifica."
}
Regole:
- massimo {max_calls} calls;
- per una richiesta generica o complessa preferisci 1 call a vulkan_helper con richiesta completa;
- usa piu' calls solo se la richiesta contiene sotto-task indipendenti o richiede prima status/read e poi fix;
- non chiamare endpoint statici bypassando il bridge;
- se la richiesta chiede applicazione patch, usa safe_write_lab salvo consenso esplicito a operazioni distruttive.
""".strip().format(max_calls=self.valves.MAX_BRIDGE_CALLS)
        context = {
            "body_model": body.get("model"),
            "user_id": (user or {}).get("id") if isinstance(user, dict) else None,
            "pipeline": self.valves.PIPELINE_ID,
        }
        payload = {
            "model": self.valves.PLANNER_MODEL,
            "stream": False,
            "temperature": self.valves.MODEL_TEMPERATURE,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps({"user_request": user_request, "context": context}, ensure_ascii=False)},
            ],
        }
        result = self._post_openwebui_chat(payload, timeout=self.valves.PLANNER_TIMEOUT_SECONDS)
        text = self._message_text(result)
        parsed = self._parse_json_object(text)
        if not parsed:
            return {
                "intent": "coding",
                "needs_bridge": True,
                "risk": self.valves.DEFAULT_APPROVAL_MODE,
                "rationale": "fallback_after_invalid_planner_json",
                "planner_raw": text[:6000],
                "calls": [self._default_call(user_request)],
                "final_answer_policy": "Use only bridge evidence.",
            }
        return parsed

    def _normalize_calls(self, plan: dict[str, Any], user_request: str) -> list[dict[str, Any]]:
        raw_calls = plan.get("calls") if isinstance(plan, dict) else None
        if not isinstance(raw_calls, list) or not raw_calls:
            raw_calls = [self._default_call(user_request)]
        calls: list[dict[str, Any]] = []
        for raw in raw_calls[: self.valves.MAX_BRIDGE_CALLS]:
            if not isinstance(raw, dict):
                continue
            request = str(raw.get("request") or raw.get("task") or user_request).strip()
            if not request:
                continue
            approval = str(raw.get("approval_mode") or plan.get("risk") or self.valves.DEFAULT_APPROVAL_MODE).strip()
            if approval not in {"read_only", "safe_write_lab", "requires_user_consent"}:
                approval = self.valves.DEFAULT_APPROVAL_MODE
            function = str(raw.get("function") or "vulkan_helper").strip()
            if function not in {"", "vulkan_helper", "repo_status", "repo_search", "repo_read", "repo_command", "repo_capabilities"}:
                function = "vulkan_helper"
            calls.append(
                {
                    "title": str(raw.get("title") or function or "vulkan step").strip()[:120],
                    "request": request,
                    "function": function,
                    "approval_mode": approval,
                    "return_mode": str(raw.get("return_mode") or self.valves.DEFAULT_RETURN_MODE),
                    "wait_seconds": self._safe_int(raw.get("wait_seconds"), self.valves.BRIDGE_WAIT_SECONDS),
                }
            )
        return calls or [self._default_call(user_request)]

    def _default_call(self, user_request: str) -> dict[str, Any]:
        return {
            "title": "vulkan_helper full task",
            "request": user_request,
            "function": "vulkan_helper",
            "approval_mode": self.valves.DEFAULT_APPROVAL_MODE,
            "return_mode": self.valves.DEFAULT_RETURN_MODE,
            "wait_seconds": self.valves.BRIDGE_WAIT_SECONDS,
        }

    def _call_bridge(self, call: dict[str, Any], index: int, total: int) -> dict[str, Any]:
        bridge_payload = {
            "request": call["request"],
            "task": call["request"],
            "function": call.get("function") or "vulkan_helper",
            "tool_name": call.get("function") or "vulkan_helper",
            "mode": "openwebui_pipeline_controller",
            "controller": "aicarmine_vulkan_controller_pipeline",
            "controller_step": index,
            "controller_total_steps": total,
            "approval_mode": call.get("approval_mode") or self.valves.DEFAULT_APPROVAL_MODE,
            "return_mode": call.get("return_mode") or self.valves.DEFAULT_RETURN_MODE,
            "wait_seconds": call.get("wait_seconds") or self.valves.BRIDGE_WAIT_SECONDS,
            "timeout_seconds": self.valves.BRIDGE_TIMEOUT_SECONDS,
            "context": (
                "Called by OpenWebUI Pipeline controller. Preserve dynamic bridge->3572 planner semantics; "
                "do not treat this as a static helper-only request."
            ),
        }
        started = time.time()
        try:
            result = self._post_json(self.valves.VULKAN_BRIDGE_URL, bridge_payload, timeout=self.valves.BRIDGE_TIMEOUT_SECONDS)
            ok = bool(result.get("ok", True)) if isinstance(result, dict) else True
            return {
                "ok": ok,
                "step": index,
                "title": call.get("title"),
                "request": call.get("request"),
                "function": call.get("function"),
                "elapsed_seconds": round(time.time() - started, 3),
                "bridge_url": self.valves.VULKAN_BRIDGE_URL,
                "result": self._compact(result, self.valves.MAX_OBSERVATION_CHARS),
            }
        except Exception as exc:
            return {
                "ok": False,
                "step": index,
                "title": call.get("title"),
                "request": call.get("request"),
                "function": call.get("function"),
                "elapsed_seconds": round(time.time() - started, 3),
                "bridge_url": self.valves.VULKAN_BRIDGE_URL,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }

    def _synthesize(self, user_request: str, plan: dict[str, Any], observations: list[dict[str, Any]]) -> str:
        system = """
Sei il synthesizer finale di una Pipeline OpenWebUI per coding/debug.
Devi rispondere in italiano tecnico, diretto, senza inventare evidenze.
Usa solo osservazioni e risultati bridge forniti.
Quando possibile separa:
- Sintomo
- Evidenza
- Causa confermata o causa non ancora confermata
- Fix minimo
- Verifica
Se il bridge ha prodotto patch, diff, file o comando di verifica, riportali in modo operativo.
Se il bridge e' irraggiungibile o incompleto, dillo chiaramente e indica il test minimo.
Non stampare JSON grezzo salvo sia l'unica evidenza utile.
""".strip()
        context = {
            "user_request": user_request,
            "outer_plan": self._compact(plan, 16000),
            "bridge_observations": observations,
        }
        payload = {
            "model": self.valves.SYNTH_MODEL,
            "stream": False,
            "temperature": self.valves.MODEL_TEMPERATURE,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(context, ensure_ascii=False, indent=2)[: self.valves.MAX_FINAL_CONTEXT_CHARS]},
            ],
        }
        try:
            result = self._post_openwebui_chat(payload, timeout=self.valves.SYNTH_TIMEOUT_SECONDS)
            text = self._message_text(result).strip()
            if text:
                return text
        except Exception as exc:
            return self._fallback_summary(user_request, plan, observations, synth_error=exc)
        return self._fallback_summary(user_request, plan, observations, synth_error=None)

    def _post_openwebui_chat(self, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
        base = self.valves.OPENWEBUI_BASE_URL.rstrip("/")
        headers = {"Content-Type": "application/json; charset=utf-8"}
        if self.valves.OPENWEBUI_API_KEY.strip():
            headers["Authorization"] = "Bearer " + self.valves.OPENWEBUI_API_KEY.strip()
        return self._post_json(base + "/api/chat/completions", payload, timeout=timeout, headers=headers)

    def _post_json(
        self,
        url: str,
        payload: dict[str, Any],
        timeout: int,
        headers: Optional[dict[str, str]] = None,
    ) -> dict[str, Any]:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers=headers or {"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
                status = getattr(response, "status", 200)
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code} from {url}: {raw[:2000]}") from exc
        if status < 200 or status >= 300:
            raise RuntimeError(f"HTTP {status} from {url}: {raw[:2000]}")
        try:
            decoded = json.loads(raw) if raw.strip() else {}
        except Exception as exc:
            raise RuntimeError(f"Invalid JSON from {url}: {raw[:2000]}") from exc
        return decoded if isinstance(decoded, dict) else {"ok": True, "value": decoded}

    def _message_text(self, result: dict[str, Any]) -> str:
        choices = result.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                msg = first.get("message")
                if isinstance(msg, dict) and isinstance(msg.get("content"), str):
                    return msg["content"]
                if isinstance(first.get("text"), str):
                    return first["text"]
        for key in ("response", "content", "message", "text"):
            if isinstance(result.get(key), str):
                return result[key]
        return json.dumps(result, ensure_ascii=False)

    def _parse_json_object(self, text: str) -> dict[str, Any]:
        raw = str(text or "").strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.lower().startswith("json"):
                raw = raw[4:].strip()
        candidates = [raw]
        start, end = raw.find("{"), raw.rfind("}")
        if start >= 0 and end > start:
            candidates.append(raw[start : end + 1])
        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                continue
        return {}

    def _compact(self, value: Any, limit: int) -> Any:
        text = json.dumps(value, ensure_ascii=False, default=str)
        if len(text) <= limit:
            return value
        return {
            "compacted": True,
            "original_chars": len(text),
            "preview": text[: max(0, limit - 200)],
            "note": "Truncated by OpenWebUI Pipeline controller; increase MAX_OBSERVATION_CHARS if needed.",
        }

    def _fallback_summary(
        self,
        user_request: str,
        plan: dict[str, Any],
        observations: list[dict[str, Any]],
        synth_error: Optional[BaseException],
    ) -> str:
        ok_count = sum(1 for item in observations if item.get("ok"))
        lines = [
            "## Risultato Pipeline",
            "",
            "**Sintomo**",
            "La sintesi finale tramite modello OpenWebUI non ha prodotto testo valido." if synth_error is None else f"La sintesi finale ha fallito: `{type(synth_error).__name__}: {synth_error}`.",
            "",
            "**Evidenza**",
            f"Richiesta utente: `{user_request[:500]}`",
            f"Step bridge completati: {ok_count}/{len(observations)}.",
            "",
            "**Causa**",
            "Il controller ha eseguito gli step, ma il passaggio finale LLM non e' disponibile o non e' conforme.",
            "",
            "**Fix minimo**",
            "Verifica `OPENWEBUI_BASE_URL`, `OPENWEBUI_API_KEY`, `SYNTH_MODEL` e raggiungibilita' di `/api/chat/completions` dal container Pipelines.",
            "",
            "**Osservazioni compatte**",
            "```json",
            json.dumps({"plan": plan, "observations": observations}, ensure_ascii=False, indent=2)[:20000],
            "```",
        ]
        return "\n".join(lines)

    async def _emit(self, emitter: EventEmitter, kind: str, description: str, done: bool) -> None:
        if emitter is None:
            return
        payload = {"type": kind, "data": {"description": description, "done": done}}
        try:
            maybe = emitter(payload)
            if hasattr(maybe, "__await__"):
                await maybe
        except Exception:
            return

    def _sectioned_error(self, symptom: str, evidence: str, cause: str, fix: str) -> str:
        return (
            "**Sintomo**\n"
            f"{symptom}\n\n"
            "**Evidenza**\n"
            f"{evidence}\n\n"
            "**Causa**\n"
            f"{cause}\n\n"
            "**Fix minimo**\n"
            f"{fix}"
        )

    def _safe_int(self, value: Any, default: int) -> int:
        try:
            return int(value)
        except Exception:
            return int(default)
