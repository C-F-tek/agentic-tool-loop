"""Dynamic tool surface controller for planner loop.

Calcola suggerimenti dinamici per gli strumenti disponibili nel turno corrente
basandosi su stato dell'evidence contract, storio dei turni, classificazione
semantica del goal e pattern di rejection dal validator.

I suggerimenti NON bloccano nulla — sono hint che il planner può ignorare se ha
buone ragioni. Il filtro primario rimane ToolSurfacePolicy; questi suggerimenti
arricchiscono solo il prompt e possono essere usati come prioritized filter.

CRITICO: I tool decisionali/terminali (planner_decision, final_answer, ecc.)
vengono ESCLUSI dai suggerimenti dinamici finché le pre-condizioni di chiusura
non sono soddisfatte (_check_final_preconditions restituisce True). Questo evita
che l'IA scelga prematuramente "final" basandosi sul prompt senza completare le
letture e la coverage necessarie.
"""

from __future__ import annotations

from typing import Any


class DynamicToolSurfaceController:
    """Calcola suggerimenti dinamici per gli strumenti disponibili nel turno corrente.

    Il controller analizza lo stato del loop e produce una lista ordinata di
    tool suggestions con punteggio di rilevanza (0-100). I suggerimenti non
    bloccano nulla — sono hint che il planner può ignorare se ha buone ragioni.
    
    CRITICO: I tool terminali vengono filtrati via da _dedupe_and_sort() quando
    le precondizioni di chiusura non sono soddisfatte.
    """

    # Mapping tra tipo di file letto e tool correlati
    _FILE_TYPE_TOOL_MAP: dict[str, list[str]] = {
        ".py": ["repo_ruff_check", "repo_pyright_check"],  # Python → linting/type check
        ".sh": ["repo_shellcheck"],                          # Shell → shellcheck
        ".json": ["repo_jq_query"],                         # JSON → jq query
        ".yaml": [],                                        # YAML/YML → no specific tool yet
        ".yml": [],                                         # YML → no specific tool yet
        ".toml": [],                                        # TOML → no specific tool yet
        ".md": [],                                          # Markdown → no specific tool yet
        ".txt": [],                                         # Text → no specific tool yet
        ".xml": [],                                         # XML → no specific tool yet
        ".html": [],                                        # HTML → no specific tool yet
        ".css": [],                                         # CSS → no specific tool yet
        ".js": ["repo_semgrep_scan"],                      # JS → semgrep for security scan
        ".ts": ["repo_semgrep_scan"],                      # TS → semgrep for security scan
        ".go": ["repo_command"],                            # Go → go vet/golangci-lint via command
        ".rs": ["repo_command"],                            # Rust → cargo check/rustfmt via command
        ".c": ["repo_command"],                             # C → gcc -fsyntax-only via command
        ".h": [],                                           # Header → no specific tool yet
    }

    # Mapping tra goal class e strumenti base suggeriti
    _GOAL_CLASS_TOOL_MAP: dict[str, list[str]] = {
        "analysis_only": ["repo_status", "repo_tree", "repo_search"],
        "code_product_report": [
            "repo_read", "repo_list_files", "repo_search",
            "repo_propose_code_edit", "planner_scratchpad_write"
        ],
        "apply_write": [
            "repo_read", "repo_list_files", "repo_search",
            "repo_apply_patch", "repo_validate", "repo_command"
        ],
        "code_security_analysis": [
            "repo_semgrep_scan", "repo_ast_grep_search", "repo_read"
        ],
        "generic": ["repo_capabilities", "vulkan_helper"],
    }

    # Tool decisionali/terminali da escludere dai suggerimenti dinamici
    # finché _check_final_preconditions() non restituisce True.
    # Questo è il filtro principale contro la terminazione prematura dell'IA.
    _TERMINAL_TOOL_NAMES: frozenset[str] = frozenset((
        "planner_decision",
        "final_answer",
        "finalize",
        "complete",
        "finish",
        "done",
        "close",
        "terminate",
        "end_job",
        "job_complete",
        "job_done",
        "task_complete",
        "task_done",
        "report_complete",
        "analysis_complete",
        "review_complete",
        "summary_complete",
        "conclusion",
        "closing_remarks",
        "final_report",
        "quality_assessment",
        "final_quality_check",
        "judge_fallback",
        "terminal_judge",
        "openwebui_terminal_answer",
    ))


    def suggest_tools(
        self,
        goal: str,
        evidence_contract: dict[str, Any],
        history: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Calcola suggerimenti dinamici per gli strumenti disponibili nel turno corrente.

        Args:
            goal: Goal dell'utente (es. "analizza services/aicarmine_broker")
            evidence_contract: Contract attuale con candidate_next_actions,
                coverage_satisfied, required_next_tool_call, ecc.
            history: Storico dei turni precedenti

        Returns:
            Lista ordinata di dicts con struttura:
            {
                "tool": "nome_tool",
                "score": 95,           # Punteggio 0-100
                "reason": "lettura file .py completata → suggerisco linting",
                "category": "post-read-suggestion",  # Per debugging
            }
        
        CRITICO: I tool terminali vengono filtrati via se le precondizioni
        di chiusura non sono soddisfatte (_check_final_preconditions restituisce False).
        """
        suggestions: list[dict[str, Any]] = []

        # Step 1: Suggerimenti basati su goal classification
        suggestions.extend(self._suggest_from_goal_classification(evidence_contract))

        # Step 2: Suggerimenti basati su tipo di file letto
        suggestions.extend(self._suggest_from_read_history(history))

        # Step 3: Suggerimenti basati su rejection patterns
        suggestions.extend(self._suggest_from_rejections(goal, evidence_contract, history))

        # Step 4: Suggerimenti basati su progress state
        suggestions.extend(
            self._suggest_from_progress_state(goal, evidence_contract, history),
        )

        # Deduplica e ordina per score — filtra anche i tool terminali prematuri
        return self._dedupe_and_sort(suggestions, goal, evidence_contract, history)


    def _suggest_from_goal_classification(
        self,
        evidence_contract: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Suggerisci strumenti in base alla classificazione semantica del goal.

        Estrae semantic_goal_classification dall'evidence contract e mappa la
        classificazione a una lista di tool appropriati con score base 50.
        
        CRITICO: I tool terminali presenti nella map vengono filtrati via se le
        precondizioni non sono soddisfatte.
        """
        semantic = evidence_contract.get("semantic_goal_classification", {})
        if not isinstance(semantic, dict):
            return []

        goal_class = str(semantic.get("class") or "").strip()
        tool_list = self._GOAL_CLASS_TOOL_MAP.get(goal_class, [])

        if not tool_list:
            return []

        return [
            {
                "tool": name,
                "score": 50,
                "reason": f"Goal classification '{goal_class}' suggests this tool",
                "category": "goal-class-suggestion",
            }
            for name in tool_list
        ]


    def _suggest_from_read_history(
        self,
        history: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Dai file letti nei turni precedenti, suggerisci tool correlati.

        Analizza quali file sono stati letti con successo (repo_read o
        planner_scratchpad_write con code_product_build_state) e suggerisce
        strumenti basati sull'estensione del file.
        
        CRITICO: I tool terminali vengono filtrati via se le precondizioni non
        sono soddisfatte.
        """
        read_paths = self._extract_successful_read_paths(history)

        suggestions: list[dict[str, Any]] = []
        for path in read_paths:
            suffix = self._get_file_suffix(path)

            if not suffix or suffix not in self._FILE_TYPE_TOOL_MAP:
                continue

            correlated_tools = self._FILE_TYPE_TOOL_MAP[suffix]
            for tool_name in correlated_tools:
                # Controlla se questo tool è già stato usato dopo la lettura di questo path
                if not self._is_tool_already_used_after_read(tool_name, path, history):
                    suggestions.append({
                        "tool": tool_name,
                        "score": 75,
                        "reason": (
                            f"File '{path}' ({suffix}) letto → {tool_name} potrebbe essere utile"
                        ),
                        "category": "post-read-suggestion",
                        "trigger_path": path,
                    })

        return suggestions


    def _suggest_from_rejections(
        self,
        goal: str,
        evidence_contract: dict[str, Any],
        history: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Dopo una rejection del validator, suggerisci tool alternativi.

        Cerca l'ultima rejection nello storico e suggerisce alternative basate
        sui violation patterns (es. repo_read_already_successful → scratchpad_write).
        
        CRITICO: I tool terminali (final_answer) vengono ESCLUSI finché le pre-condizioni
        di chiusura non sono soddisfatte (_check_final_preconditions restituisce True),
        anche se la rejection è "no_progress_made". Questo evita che l'IA scelga
        prematuramente final solo perché vede il pattern di rejection.
        """
        last_rejection = self._find_last_rejection(history)
        if not last_rejection:
            return []

        rejected_tool = str(last_rejection.get("rejected_tool") or "").strip()
        violations = last_rejection.get("violations", [])

        # Fallback per debug
        if not violations and isinstance(rejected_tool, str):
            pass  # No specific suggestion for unknown violations

        suggestions: list[dict[str, Any]] = []

        for violation in violations:
            violation_text = str(violation).lower()

            if "repo_read_already_successful" in violation_text:
                suggestions.append({
                    "tool": "planner_scratchpad_write",
                    "score": 80,
                    "reason": (
                        f"Rejection: {violation}. Suggerisco di scrivere un progresso invece di ripetere la lettura."
                    ),
                    "category": "rejection-alternative",
                })

            elif "missing_path_or_paths_items" in violation_text:
                suggestions.append({
                    "tool": "repo_list_files",
                    "score": 65,
                    "reason": (
                        f"Rejection: {violation}. Suggerisco prima di listare i file per identificare il path corretto."
                    ),
                    "category": "rejection-alternative",
                })

            # NOTE: Il blocco con final_answer è stato rimosso. Ora final_answer viene
            # gestito solo quando le precondizioni sono verificate esplicitamente tramite
            # _check_final_preconditions() nel call site che necessita del goal e
            # evidence_contract completi. Questo evita che l'IA scelga prematuramente
            # "final_answer" basandosi solo su una rejection pattern senza verificare
            # che tutte le letture e la coverage siano state completate.


    def _suggest_from_progress_state(
        self,
        goal: str,
        evidence_contract: dict[str, Any],
        history: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Suggerisci strumenti basati sullo stato attuale del progresso.

        Controlla required_next_tool_call pendente, coverage non soddisfatto e
        candidate_next_actions per suggerire azioni prioritarie.
        
        CRITICO: I tool decisionali/terminali (planner_decision, final_answer, ecc.)
        vengono ESCLUSI dai suggerimenti dinamici finché le pre-condizioni di
        finalizzazione non sono soddisfatte (_check_final_preconditions restituisce True).
        Questo evita che l'IA scelga prematuramente "final" solo perché è presente
        tra i suggerimenti nel prompt.
        """
        suggestions: list[dict[str, Any]] = []

        # Step 1: Controlla se c'è un required_next_tool_call pendente
        required = evidence_contract.get("required_next_tool_call", {})
        if isinstance(required, dict) and required.get("validated"):
            tool_name = str(required.get("tool") or "").strip()
            normalized_target = self._normalize_tool_name(tool_name)
            
            # Verifica se questo tool è terminale/decisionale
            _is_terminal_allowed = False
            if normalized_target in self._TERMINAL_TOOL_NAMES:
                # Permetti SOLO se tutte le precondizioni finali sono soddisfatte
                is_ready, _reasons = self._check_final_preconditions(goal, evidence_contract, history)
                _is_terminal_allowed = is_ready
            
            if not _is_terminal_allowed:
                # Tool terminale ma precondizioni NON soddisfatte → escludi
                pass
            else:
                suggestions.append({
                    "tool": tool_name,
                    "score": 95,
                    "reason": f"required_next_tool_call dal contract: {tool_name}",
                    "category": "contract-required",
                })

        # Step 2: Controlla se coverage non è soddisfatto
        coverage_satisfied = evidence_contract.get("coverage_satisfied") is True
        missing_paths = evidence_contract.get("missing_owner_paths", [])

        if not coverage_satisfied and isinstance(missing_paths, list):
            for path in (missing_paths[:3] if len(missing_paths) > 0 else []):
                suggestions.append({
                    "tool": "repo_read",
                    "score": 85,
                    "reason": f"Coverage non soddisfato. Path mancante da leggere: {path}",
                    "category": "coverage-mandatory",
                    "trigger_path": path,
                })

            # Se repo_read non funziona, suggerisci search come alternativa
            suggestions.append({
                "tool": "repo_search",
                "score": 60,
                "reason": "Se repo_read fallisce, prova con repo_search per trovare il file.",
                "category": "coverage-alternative",
            })

        # Step 3: Controlla se ci sono candidate_next_actions estraibili
        candidates = evidence_contract.get("candidate_next_actions", [])
        if isinstance(candidates, list) and len(candidates) > 0:
            first_candidate = candidates[0] if isinstance(candidates[0], dict) else {}
            tool_name = str(first_candidate.get("tool") or "").strip()
            
            if tool_name:
                normalized_target = self._normalize_tool_name(tool_name)
                
                # Verifica se questo tool è terminale/decisionale
                _is_terminal_allowed = False
                if normalized_target in self._TERMINAL_TOOL_NAMES:
                    is_ready, _reasons = self._check_final_preconditions(goal, evidence_contract, history)
                    _is_terminal_allowed = is_ready
                
                if not _is_terminal_allowed:
                    pass  # Escludi tool terminali prematuramente
                else:
                    suggestions.append({
                        "tool": tool_name,
                        "score": 70,
                        "reason": f"Primo candidate_next_action dal contract: {tool_name}",
                        "category": "contract-candidate",
                    })

        return suggestions


    def _check_final_preconditions(
        self, 
        goal: str,
        evidence_contract: dict[str, Any],
        history: list[dict] | None = None,
    ) -> tuple[bool, list[str]]:
        """Verifica tutte le pre-condizioni per permettere tool decisionali/terminali.

        Questo metodo controlla che:
        1. coverage_satisfied == True (tutte le letture richieste completate)
        2. missing_owner_paths == [] (nessun path mancante)
        3. required_next_tool_call non pendente
        4. finalization_contract.final_allowed == True
        5. Non in rewrite_latch con stato insoddisfatto
        
        CRITICO: Se restituisce (True, []), allora i tool terminali possono essere
        inclusi nei suggerimenti dinamici senza rischio di terminazione prematura.

        Args:
            goal: Goal dell'utente (usato solo per logging/debug)
            evidence_contract: Contract attuale del planner
            history: Storico dei turni (opzionale, usato da _is_final_ready)

        Returns:
            Tuple di (precondizioni_soddisfatte, lista_motivi_non_soddisfatti)
        """
        reasons_not_ready: list[str] = []

        # Pre-condizione 1: Coverage letture soddisfatte
        coverage_satisfied = evidence_contract.get("coverage_satisfied") is True
        if not coverage_satisfied:
            reasons_not_ready.append(
                "coverage_satisfied=false — non tutte le letture richieste sono state completate"
            )

        # Pre-condizione 2: No missing owner paths
        missing_paths = evidence_contract.get("missing_owner_paths", [])
        if isinstance(missing_paths, list) and len(missing_paths) > 0:
            reasons_not_ready.append(
                f"missing_owner_paths={missing_paths[:5]} — path mancanti da leggere"
            )

        # Pre-condizione 3: No required_next_tool_call pendente
        required = evidence_contract.get("required_next_tool_call", {})
        if isinstance(required, dict) and required.get("validated"):
            reasons_not_ready.append(
                f"required_next_tool_call pendente: {required.get('tool')}"
            )

        # Pre-condizione 4: Planner può scegliere final
        final_allowed = (
            evidence_contract.get("finalization_contract", {}).get("final_allowed") is True
        )
        if not final_allowed:
            reasons_not_ready.append("finalization_contract.final_allowed=false")

        # Pre-condizione 5: Non in rewrite_latch con tool insoddisfatto
        latch = str(evidence_contract.get("final_rewrite_latch") or "").strip()
        if latch and latch != "rewrite_required":
            reasons_not_ready.append(f"in final_rewrite_latch state: {latch}")

        # Pre-condizione 6 (opzionale): Verifica _is_final_ready se history disponibile
        # Questo aggiunge un ulteriore filtro di sicurezza basato sul numero di letture effettuate
        if history is not None:
            if not self._is_final_ready(history):
                reasons_not_ready.append(
                    "_is_final_ready=False — meno di 3 file letti o loop di lettura rilevato"
                )

        return (len(reasons_not_ready) == 0), reasons_not_ready


    def _extract_successful_read_paths(self, history: list[dict]) -> set[str]:
        """Estrai i path dei file letti con successo dai turni precedenti."""
        paths: set[str] = set()
        for item in history:
            if not isinstance(item, dict):
                continue
            
            result = item.get("tool_result") if isinstance(item.get("tool_result"), dict) else {}
            if result.get("ok") is not True:
                continue
            
            tool = str(result.get("tool") or "").strip().lower()

            if tool == "repo_read":
                # Estrai il path dal risultato o dalla decisione
                path = result.get("path") or result.get("repo_path")
                if path and path != ".":
                    paths.add(str(path))
            
            elif tool == "planner_scratchpad_write":
                # Controlla se è stato scritto un code_product_build_state
                text = result.get("text") or result.get("content") or ""
                if "code_product_build_state" in text:
                    try:
                        import json
                        payload = json.loads(text)
                        target_file = payload.get("target_file", "")
                        if target_file:
                            paths.add(target_file)
                    except Exception:
                        pass
        
        return paths


    def _get_file_suffix(self, path: str) -> str:
        """Estrai l'estensione del file.

        Cerca le chiavi in _FILE_TYPE_TOOL_MAP e restituisce la prima che matcha.
        """
        path_lower = path.lower()
        for suffix in self._FILE_TYPE_TOOL_MAP.keys():
            if path_lower.endswith(suffix):
                return suffix
        return ""


    def _is_tool_already_used_after_read(
        self, 
        tool_name: str, 
        read_path: str, 
        history: list[dict]
    ) -> bool:
        """Controlla se questo tool è già stato usato dopo la lettura di questo path.

        Cerca pattern temporale: repo_read(path) → tool_name nella stessa finestra.
        """
        # Normalizza il nome del tool (gestisce alias)
        normalized_target = self._normalize_tool_name(tool_name)
        
        found_reads = False
        for item in reversed(history[-10:] if len(history) >= 10 else history):
            if not isinstance(item, dict):
                continue
            
            result = item.get("tool_result") if isinstance(item.get("tool_result"), dict) else {}
            decision = item.get("decision") if isinstance(item.get("decision"), dict) else {}
            
            tool = str(result.get("tool") or decision.get("tool") or "").strip().lower()

            if tool == "repo_read":
                path = result.get("path") or result.get("repo_path")
                if path == read_path:
                    found_reads = True
            
            elif self._normalize_tool_name(tool) == normalized_target:
                if found_reads:
                    return True
        
        return False


    def _find_last_rejection(self, history: list[dict]) -> dict | None:
        """Trova l'ultima rejection dal controller guard."""
        for item in reversed(history):
            if not isinstance(item, dict):
                continue
            
            result = item.get("tool_result") if isinstance(item.get("tool_result"), dict) else {}
            
            # Cerca nel risultato del tool o nella decisione
            violations = result.get("violations") or []
            rejected_decision = result.get("rejected_decision") or {}
            
            if violations and rejected_decision:
                return {
                    "rejected_tool": str(rejected_decision.get("tool") or ""),
                    "violations": violations,
                }
        
        return None


    def _is_final_ready(self, history: list[dict]) -> bool:
        """Controlla se il planner è pronto per final (tutte le letture fatte).

        Almeno 3 file diversi letti e non più di 1 ripetizione negli ultimi 5 turni.
        """
        read_paths: set[str] = set()
        for item in history:
            if not isinstance(item, dict):
                continue
            result = item.get("tool_result", {})
            if result.get("ok") is True and result.get("tool") == "repo_read":
                path = result.get("path") or ""
                if path:
                    read_paths.add(path)
        
        # Controlla gli ultimi 5 turni per loop di lettura
        recent_reads = [
            i for i in reversed(history[-5:]) 
            if isinstance(i, dict) and i.get("tool_result", {}).get("tool") == "repo_read"
        ]
        unique_recent = len(
            set(r.get("tool_result", {}).get("path") for r in recent_reads)
        )
        
        return len(read_paths) >= 3 and unique_recent <= 1


    def _dedupe_and_sort(
        self, 
        suggestions: list[dict[str, Any]],
        goal: str,
        evidence_contract: dict[str, Any],
        history: list[dict] | None,
    ) -> list[dict[str, Any]]:
        """Deduplica e ordina i suggerimenti per punteggio.

        Se un tool appare più volte, mantiene il suggestion con score più alto.
        Restituisce max 8 suggerimenti unici.
        
        CRITICO: I tool terminali vengono ESCLUSI se le precondizioni non sono
        soddisfatte (_check_final_preconditions restituisce False). Questo è il
        filtro principale contro la terminazione prematura dell'IA.
        """
        seen_tools: set[str] = set()
        unique_suggestions: list[dict[str, Any]] = []
        
        # Ordina per score decrescente prima della deduplica
        sorted_sugs = sorted(suggestions, key=lambda x: -x["score"])
        
        for s in sorted_sugs:
            tool_name = s["tool"]
            
            # Verifica se questo tool è terminale/decisionale
            normalized_target = self._normalize_tool_name(tool_name)
            if normalized_target in self._TERMINAL_TOOL_NAMES:
                # Controlla se le precondizioni finali sono soddisfatte
                is_ready, _reasons = self._check_final_preconditions(
                    goal, evidence_contract, history
                )
                if not is_ready:
                    # Tool terminale ma precondizioni NON soddisfatte → escludi
                    continue
            
            # Mantieni il primo (più alto score) e ignora i duplicati
            if tool_name not in seen_tools:
                seen_tools.add(tool_name)
                unique_suggestions.append(s)
        
        return unique_suggestions[:8]  # Max 8 suggerimenti


    @staticmethod
    def _normalize_tool_name(name: str) -> str:
        """Normalizza il nome del tool gestendo alias e casi."""
        # Mapping semplificato degli alias comuni
        aliases: dict[str, str] = {
            "ruff_check": "repo_ruff_check",
            "pyright_check": "repo_pyright_check",
            "shellcheck": "repo_shellcheck",
            "jq_query": "repo_jq_query",
            "semgrep_scan": "repo_semgrep_scan",
            "ast_grep_search": "repo_ast_grep_search",
            "propose_code_edit": "repo_propose_code_edit",
            "apply_patch": "repo_apply_patch",
            "write_file": "repo_write_file",
        }
        
        name_lower = name.strip().lower()
        return aliases.get(name_lower, name_lower)
