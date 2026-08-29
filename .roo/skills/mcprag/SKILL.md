---
name: mcprag
description: Guida operativa completa per l'uso dell'MCP RAG server (aicarmine-rag-global v2.0.0) come strumento primario di ricerca full-text nel codice e nei documenti del progetto. Include workflow, best practices, parametri ottimizzati ed esempi concreti.
---

# Mcprag — AICarmine Global RAG MCP Server Skill

## Overview

Il **aicarmine-rag-global** MCP server (v2.0.0) fornisce ricerca full-text basata su FTS5 SQLite attraverso qualsiasi base codice sotto `C:\Users\someo\`. Crea automaticamente un database SQLite separato per ogni path unico, permettendo di indicizzare multipli repository senza conflitti.

| Proprietà | Valore |
|-----------|--------|
| **Server name** | `aicarmine-rag` |
| **Versione** | 2.0.0 |
| **Transport** | stdio (JSON-RPC) |
| **DB root** | `C:\Users\someo\AI\state\codex_rag_global\` |
| **Database engine** | SQLite con FTS5 (Full-Text Search) |
| **Reranker opzionale** | OVMS BAAI/bge-reranker-v2-m3 su porta 3550 |

---

## Esposed Tools (Strumenti Disponibili)

| Tool | Descrizione | Quando Usare |
|------|-------------|--------------|
| `aicarmine_rag_search` | Cerca nel RAG index con FTS5 full-text search | **Principale strumento di ricerca**. Usa quando devi trovare codice, documentazione, pattern API, funzioni, classi o qualsiasi contenuto testuale nei file del progetto. |
| `aicarmine_rag_index_status` | Ispeziona lo stato dell'index e la sua freschezza | Prima di cercare, verifica se l'index è aggiornato rispetto al Git HEAD corrente. Controlla anche il numero di chunk/files indicizzati. |
| `aicarmine_rag_reindex` | Costruisce o ricostruisce l'RAG index | Dopo modifiche significative ai file, dopo un pull/push Git, o quando i risultati di ricerca sono incompleti/obsoleti. Supporta modalità "delta" (incrementale) e "full". |
| `aicarmine_rag_health` | Health check per il server globale RAG | Verifica che il server sia attivo prima di eseguire operazioni pesanti. Utile in diagnostica iniziale. |

---

## Workflow Tipico di Ricerca

### Step 1: Verificare Salute Server

```json
{
  "method": "tools/call",
  "params": {
    "name": "aicarmine_rag_health",
    "arguments": {}
  }
}
```

**Cosa cercare nella risposta:**
- `"ok": true` → Server operativo
- Errori di connessione → Riprova o riavvia il server MCP

### Step 2: Controllare Stato Index

```json
{
  "method": "tools/call",
  "params": {
    "name": "aicarmine_rag_index_status",
    "arguments": {
      "search_path": "C:\\Users\\someo\\agentic-tool-loop"
    }
  }
}
```

**Campi chiave della risposta:**
- `stale`: boolean — `true` se l'index è obsoleto rispetto al working tree
- `current_commit`: commit Git HEAD corrente
- `indexed_commit`: commit indicizzato (vuoto per filesystem mode)
- `db_status.tables`: tabelle SQLite con conteggi righe (`chunks`, `files`, `index_meta`)

**Decisione:** Se `stale == true` o i conteggi sono zero/insufficienti, procedere allo Step 3.

### Step 3: Ricostruire Index (se necessario)

#### Modalità Full (ricomincia da capo):
```json
{
  "method": "tools/call",
  "params": {
    "name": "aicarmine_rag_reindex",
    "arguments": {
      "search_path": "C:\\Users\\someo\\agentic-tool-loop",
      "source": "filesystem",
      "mode": "full"
    }
  }
}
```

#### Modalità Delta (incrementale, più veloce):
```json
{
  "method": "tools/call",
  "params": {
    "name": "aicarmine_rag_reindex",
    "arguments": {
      "search_path": "C:\\Users\\someo\\agentic-tool-loop",
      "source": "git",
      "mode": "delta"
    }
  }
}
```

**Risposta attesa:**
```json
{
  "ok": true,
  "tool": "aicarmine_rag_reindex",
  "search_path": "C:\\Users\\someo\\agentic-tool-loop",
  "db": "C:\\Users\\someo\\AI\\state\\codex_rag_global\\rag_ef83a7cd06af9827.sqlite3",
  "result": {
    "files_indexed": 1778,
    "chunks_indexed": 3224
  }
}
```

### Step 4: Eseguire Ricerca

```json
{
  "method": "tools/call",
  "params": {
    "name": "aicarmine_rag_search",
    "arguments": {
      "query": "cerca qui il tuo termine o frase",
      "search_path": "C:\\Users\\someo\\agentic-tool-loop",
      "top_k": 15,
      "candidate_limit": 80,
      "rerank": false
    }
  }
}
```

---

## Parametri Dettagliati per `aicarmine_rag_search`

| Parametro | Tipo | Default | Descrizione | Quando Modificare |
|-----------|------|---------|-------------|-------------------|
| `query` | string | **obbligatorio** | Testo della query di ricerca | Usa termini specifici. Evita parole generiche come "the", "and". Per pattern di codice, usa sintassi esatta (es: `"def build_chunks"`). |
| `search_path` | string | auto-detect | Path da cercare (deve essere sotto C:\Users\someo\) | Specifica esplicitamente quando cerchi in repo diversi dal workspace corrente. |
| `db` | string | auto-detect | Path DB SQLite esplicito | Di solito non serve. Usa solo se devi puntare a un DB specifico noto. |
| `candidate_limit` | int | 80 | Max candidati recuperati da FTS5 prima del filtering | Aumentare a 120-200 per query molto generiche che restituiscono pochi risultati pertinenti. Ridurre a 40 per query specifiche. |
| `top_k` | int | 12 | Chunk finali restituiti | Aumentare a 20-30 quando servono più contesto. Ridurre a 5-8 per risposte più focalizzate. |
| `max_chunk_chars` | int | 4000 | Max caratteri per chunk singolo | Lasciare default salvo casi dove i chunk sono troppo lunghi/brevi per il downstream. |
| `max_total_chars` | int | 50000 | Total characters nella risposta | Controlla la dimensione totale della risposta. Ridurre se il modello ha limiti di context window. |
| `rerank` | bool | true | Abilita reranking neurale | Disabilitare (`false`) quando il reranker è unavailable o per query veloci senza precisione. Abilitare (`true`) per massima rilevanza. |
| `rerank_candidate_limit` | int | 12 | Candidati passati al reranker | Aumentare a 20-30 se il reranker non trova abbastanza documenti rilevanti tra i top-k. |
| `rerank_doc_chars` | int | 2500 | Max chars per documento nel reranker | Di solito lasciare default. Modificare solo se i chunk sono tagliati male dal reranker. |
| `rerank_timeout_seconds` | float | 30.0 | Timeout del reranker in secondi | Aumentare se il reranker è lento (modelli grandi su CPU). |

---

## Parametri Dettagliati per `aicarmine_rag_reindex`

| Parametro | Tipo | Default | Descrizione | Quando Usare |
|-----------|------|---------|-------------|--------------|
| `search_path` | string | **obbligatorio** | Path da indicizzare | Sempre specificato esplicitamente. |
| `source` | enum | "git" | "git" o "filesystem" | Usa `"git"` quando il repo ha Git e vuoi tracciare freshness. Usa `"filesystem"` per ignore lo stato Git e indicizzare tutto ciò che esiste fisicamente. |
| `mode` | enum | "delta" | "delta" o "full" | `"delta"` è più veloce, indicizza solo le modifiche rispetto all'ultimo build. `"full"` ricomincia da zero. |
| `suffixes` | string | ".py,.md,.yaml,.yml,.json,.csv,.sql,.txt" | Estensioni file da indicizzare | Modificare per includere/escludere tipi di file specifici (es: aggiungere `.ts`, `.js`, `.go`). |
| `max_file_bytes` | int | 2000000 | Dimensione max file (2MB) | File oltre questa soglia vengono saltati. Aumentare se si indicizzano binari grandi o asset. |
| `chunk_lines` | int | 180 | Max linee per chunk | Chunk più piccoli = ricerca più precisa ma più frammentata. Chunk più grandi = meno frammentazione ma possibile rumore. |
| `chunk_chars` | int | 12000 | Max caratteri per chunk | Controlla la granularità dei chunk. Valori bassi (~5000) sono migliori per codice denso. |

---

## Best Practices per Query Efficaci

### 1. Specificità del Terminologia

**Buone query:**
- `"def build_chunks"` — cerca la definizione esatta della funzione
- `"class EvidenceBuilder"` — cerca la classe specifica
- `"MCP server configuration tool registration"` — cerca documentazione su configurazione
- `"RAG index building and chunking logic"` — cerca concetti tecnici specifici

**Query da evitare:**
- `"code"` — troppo generico, restituisce troppi risultati irrilevanti
- `"function"` — parola comune nel codice Python, quasi ogni file matcha
- `"error"` — presente in molti contesti diversi (log, commenti, eccezioni)

### 2. Pattern di Ricerca Avanzati

#### Cercare definizioni di funzioni:
```json
{ "query": "def execute_loop", "top_k": 8 }
```

#### Cercare riferimenti a un modulo/classe:
```json
{ "query": "EvidenceContract evidence_contract", "top_k": 10 }
```

#### Cercare implementazioni specifiche:
```json
{ "query": "aicarmine_rag_search FTS5 full-text search", "top_k": 5 }
```

#### Cercare documentazione o configurazioni:
```json
{ "query": "MCP server stdio JSON-RPC transport config", "top_k": 12 }
```

### 3. Ottimizzazione dei Parametri per Caso d'Uso

| Scenario | `candidate_limit` | `top_k` | `rerank` | Note |
|----------|-------------------|---------|----------|------|
| Query specifica (nome funzione/class) | 40 | 8 | false | Veloce, preciso |
| Query concettuale ("come funziona X") | 80 | 15 | true | Reranker aiuta la rilevanza |
| Ricerca esplorativa iniziale | 120 | 20 | true | Massima copertura |
| Context window limitata | 60 | 5 | false | Risposta compatta |
| Analisi approfondita | 80 | 25 | true | Più contesto, più dettagli |

---

## Variabili Ambiente

| Variabile | Default | Descrizione |
|-----------|---------|-------------|
| `AICARMINE_RAG_DB_ROOT` | `C:\Users\someo\AI\state\codex_rag_global` | Root storage database |
| `AICARMINE_RAG_REPO` | — | Path di ricerca predefinito |
| `AICARMINE_RAG_MCP_STDIO_TRANSPORT` | "jsonl" | "jsonl" o "content-length" |
| `AICARMINE_RAG_MCP_DEBUG` | "0" | Abilita logging debug |
| `AICARMINE_RAG_RERANK_URL` | `http://127.0.0.1:3550/v3/rerank` | Endpoint reranker |
| `AICARMINE_RAG_RERANK_MODEL` | `BAAI/bge-reranker-v2-m3` | Modello reranker |
| `AICARMINE_RAG_RERANK_CANDIDATE_LIMIT` | 12 | Candidati per reranker |
| `AICARMINE_RAG_RERANK_DOC_CHARS` | 2500 | Max chars per doc reranker |
| `AICARMINE_RAG_RERANK_TIMEOUT_SECONDS` | 30.0 | Timeout reranker |

---

## Validazione Path e Sicurezza

Il server **impone** che i path siano sotto `C:\Users\someo\`. I seguenti prefix sono proibiti:
- `C:\Windows`
- `C:\Program Files`
- `C:\Users\carmi`
- `C:\ProgramData`

Questo previene accessi non autorizzati a sistemi o utenti diversi.

---

## Naming Database RAG

Ogni unique search_path ottiene un database SQLite separato, nominato con hash SHA-256:

```
C:\Users\someo\AI\state\codex_rag_global\rag_<sha256_hash>.sqlite3
```

Esempi noti:
- `C:\Users\someo\agentic-tool-loop` → `rag_ef83a7cd06af9827.sqlite3`
- `C:\Users\someo\Z3l07IA` → `rag_82f17b1352f6e168.sqlite3`

Per trovare il DB esatto di un repo, usa sempre `aicarmine_rag_index_status`.

---

## Esempi Pratici Completi

### Esempio 1: Trovare implementazione planner

```json
{
  "query": "planner decision normalizer execution digest evidence",
  "search_path": "C:\\Users\\someo\\agentic-tool-loop",
  "top_k": 15,
  "candidate_limit": 80,
  "rerank": false
}
```

**Come interpretare la risposta:**
- Ogni chunk ha: `path`, `content`, `rank`, `fts_rank`, `start_line`, `end_line`, `symbol`
- Usa `path` + `start_line`/`end_line` per aprire il file nel codice sorgente
- Il campo `symbol` indica eventuali simboli rilevati (funzioni, classi)

### Esempio 2: Cercare configurazione MCP

```json
{
  "query": "MCP server configuration tool registration stdio",
  "search_path": "C:\\Users\\someo\\agentic-tool-loop",
  "top_k": 10,
  "rerank": true
}
```

### Esempio 3: Ricerca cross-repo su Z3l07IA

```json
{
  "query": "FastAPI main entry point uvicorn",
  "search_path": "C:\\Users\\someo\\Z3l07IA",
  "top_k": 8,
  "rerank": false
}
```

---

## Troubleshooting

| Problema | Causa Probabile | Soluzione |
|----------|-----------------|-----------|
| Errore `db_not_found` | Index non costruito | Esegui prima `aicarmine_rag_reindex` con source=filesystem |
| Reranker unavailable | OVMS reranker non avviato o porta sbagliata | Imposta `"rerank": false`, oppure avvia OVMS reranker su porta 3550 |
| Path validation failed | Path fuori dai permessi consentiti | Assicurati che il path sia sotto `C:\Users\someo\` e non un prefix proibito |
| Risultati vuoti / troppi irrilevanti | Query troppo generica o candidate_limit basso | Usa termini più specifici. Aumenta `candidate_limit` a 120+. Riduci `top_k` per focalizzare. |
| Index stale dopo modifiche Git | L'index non è stato aggiornato | Esegui `aicarmine_rag_index_status` → se `stale: true`, esegui `aicarmine_rag_reindex` mode=delta |
| Tempi di risposta lunghi | Reranker attivo su modello grande | Disabilita reranking (`"rerank": false`) per query veloci |

---

## Architettura del Server

```
┌─────────────────────────────────────────────────────┐
│                    Cline / MCP Client                │
└──────────────────┬──────────────────────────────────┘
                   │ stdio (JSON-RPC)
                   ▼
┌─────────────────────────────────────────────────────┐
│           aicarmine-rag-global MCP Server            │
│  ┌─────────────────────────────────────────────────┐│
│  │  aicarmine_rag_search    → FTS5 full-text search││
│  │  aicarmine_rag_reindex   → Build/rebuild index  ││
│  │  aicarmine_rag_index_status → Check freshness   ││
│  │  aicarmine_rag_health    → Server health check  ││
│  └─────────────────────────────────────────────────┘│
└──────────────────┬──────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│           SQLite RAG Database (per path)             │
│  ┌─────────────────────────────────────────────────┐│
│  │  chunks          → File content chunks          ││
│  │  chunks_fts      → FTS5 virtual table           ││
│  │  files           → Indexed file metadata        ││
│  │  index_meta      → Index configuration          ││
│  └─────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────┘
```

---

## Workflow Integrato nella Skill Mcprag — Come Usare Questo Tool

### Quando Chiamare `aicarmine_rag_search`

Usa questo tool **come tuo strumento primario di ricerca** quando:

1. Devi trovare dove è implementata una funzione, classe o metodo nel codice sorgente
2. Cerchi documentazione su come funziona un componente specifico
3. Vuoi capire il flusso di esecuzione di un modulo (es: planner loop, evidence builder)
4. Devi verificare se un pattern API esiste già prima di scrivere nuovo codice
5. Stai facendo debugging e cerchi riferimenti a variabili o log specifici

### Procedura Consigliata per Ogni Ricerca

```
1. Identifica il search_path del repo che ti interessa
2. Controlla lo stato dell'index con aicarmine_rag_index_status
3. Se stale o primo accesso, ricostruisci l'index con aicarmine_rag_reindex
4. Esegui la ricerca con query specifica e parametri ottimizzati
5. Analizza i chunk restituiti: path + start_line + end_line + symbol
6. Usa le informazioni per navigare al file/linea esatta nel codice
```

### Regole d'Oro

- **Sempre verificare lo stato dell'index PRIMA di cercare.** Un index obsoleto produce risultati incompleti.
- **Usa `rerank: false` per velocità** quando sei sicuro della specificità della query.
- **Usa `rerank: true` per precisione** quando la query è concettuale o ambigua.
- **Non usare mai query generiche** come "code", "function", "error". Sii specifico.
- **Controlla sempre i campi `path`, `start_line`, `end_line`** nei risultati per orientarti nel codice sorgente reale.
- **Se un risultato non corrisponde alla realtà**, verifica che l'index sia sincronizzato con il working tree corrente (controlla `current_commit` vs commit Git attivo).

---

## File Correlati

- [`services/codex_bridge/rag_mcp_server.py`](services/codex_bridge/rag_mcp_server.py) — Implementazione server
- [`services/codex_bridge/RAG_USAGE_GUIDE.md`](services/codex_bridge/RAG_USAGE_GUIDE.md) — Guida completa utente
- [`.vscode/mcp.json`](.vscode/mcp.json) — Config workspace MCP
- `../AppData/Roaming/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json` — Settings Cline global MCP
- [`tools/test_rag_mcp.py`](tools/test_rag_mcp.py) — Script di test funzionante
