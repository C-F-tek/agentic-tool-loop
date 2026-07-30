C:.
|   .gitignore
|   Agentic_loop_GIT_LOG_FULL.txt
|   agenti_loop_project.log
|   AGENTS.md
|   audit_mcp_allowlist.py
|   check_existing_profiles.py
|   cline_mcp_servers.json
|   debug_profiles.py
|   default
|   final_verify.py
|   find_deps_config.py
|   flow.svg
|   implementation_plan.md
|   init_mcp_databases.py
|   install_codex_app_mcp_only.ps1
|   probe_mcp_raw.py
|   probe_r4r.py
|   pytest.ini
|   qwen36-lean-show.json
|   README.md
|   run_baseline_profiles.py
|   run_mcp.bat
|   same-capability-serious-scan.json
|   storico_agentic_loop_git.log
|   test.zip
|   test_mcp_client.py
|   test_rag_mcp.py
|   tree_full.txt
|   verify_changes.py
|   
+---.clinerules
|   |   00-aicarmine-mcp-first.md
|   |   
|   \---hooks
|       |   PostToolUse.ps1
|       |   PreCompact.ps1
|       |   PreToolUse.ps1
|       |   TaskStart.ps1
|       |   UserPromptSubmit.ps1
|       |   
|       +---lib
|       |       aicarmine_cline_contract_probe.ps1
|       |       aicarmine_cline_mcp_router.ps1
|       |       aicarmine_cline_posttool_observer.ps1
|       |       aicarmine_cline_precompact_continuity.ps1
|       |       aicarmine_cline_pretool_observer.ps1
|       |       aicarmine_cline_task_bootstrap.ps1
|       |       aicarmine_pretool_symbol_injector.ps1
|       |       
|       \---tests
|               Test-AICarmineClineMcpRouter.ps1
|               Test-AICarmineClinePostToolObserver.ps1
|               Test-AICarmineClinePreCompactContinuity.ps1
|               Test-AICarmineClinePreToolObserver.ps1
|               Test-AICarmineClineTaskBootstrap.ps1
|               
+---.codex
|   |   config.toml.disabled
|   |   hooks.json
|   |   mcp_servers_probe.json
|   |   
|   +---hooks
|   |       aicarmine_mcp_probe_all.py
|   |       aicarmine_mcp_tool_log.py
|   |       
|   \---state
|           mcp_probe_report.json
|           mcp_probe_report.jsonl
|           
+---.docs
|       SYMBOL_IMPROVEMENTS.md
|       tool_symbol_reference.json
|       
+---cache
|       README.md
|       
+---code-interpreter-workdir
|       README.md
|       
+---codex_ollama_bridge_applied
|   |   AGENTS.md
|   |   aicarmine-executor-server.ps1
|   |   aicarmine-executor-server.py
|   |   aicarmine-jupyter-codeinterpreter.ps1
|   |   aicarmine-openwebui-serve.py
|   |   aicarmine-run-safe-command.ps1
|   |   aicarmine-vulkan-tool-broker.ps1
|   |   aicarmine_vulkan_bridge_server.py
|   |   aicarmine_vulkan_tool_broker.py
|   |   check-dev-toolchain.ps1
|   |   export_model.py
|   |   flow.svg
|   |   ollama-task-vulkan.ps1
|   |   openvino-env.ps1
|   |   openwebui.ps1
|   |   ovms-reranker-npu.ps1
|   |   README.md
|   |   sync-lab-from-main.ps1
|   |   watch-lab-mirror.ps1
|   |   
|   +---codex_ollama_bridge
|   |       aicarmine_codex_mcp_server.py
|   |       aicarmine_codex_ollama_responses_bridge.py
|   |       APPLIED-MAPPING.md
|   |       codex.aicarmine-ollama.config.toml
|   |       README-CODEX-OLLAMA-BRIDGE.md
|   |       README.md
|   |       start-codex-ollama-bridge.ps1
|   |       
|   \---useful_tools
|       |   flow.svg
|       |   README.md
|       |   
|       +---chunks
|       |   |   README.md
|       |   |   __init__.py
|       |   |   
|       |   +---code_chunks
|       |   |       README.md
|       |   |       __init__.py
|       |   |       
|       |   +---evidence_chunks
|       |   |       README.md
|       |   |       __init__.py
|       |   |       
|       |   \---proposal_chunks
|       |           README.md
|       |           __init__.py
|       |           
|       +---context
|       |   |   flow.svg
|       |   |   README.md
|       |   |   __init__.py
|       |   |   
|       |   +---agent_context
|       |   |   |   README.md
|       |   |   |   TOOL_CONTEXT.md
|       |   |   |   __init__.py
|       |   |   |   
|       |   |   +---agnostic_tool_inventory
|       |   |   |       cli.py
|       |   |   |       README.md
|       |   |   |       __init__.py
|       |   |   |       
|       |   |   +---ai_context_pack
|       |   |   |       builder.py
|       |   |   |       cli.py
|       |   |   |       common.py
|       |   |   |       files.py
|       |   |   |       markdown.py
|       |   |   |       profiles.py
|       |   |   |       README.md
|       |   |   |       __init__.py
|       |   |   |       
|       |   |   +---ensure_required_files
|       |   |   |       cli.py
|       |   |   |       README.md
|       |   |   |       __init__.py
|       |   |   |       
|       |   |   +---full_context_golden_proposals
|       |   |   |       cli.py
|       |   |   |       README.md
|       |   |   |       __init__.py
|       |   |   |       
|       |   |   +---local_ai_enrichment_plan
|       |   |   |       cli.py
|       |   |   |       README.md
|       |   |   |       __init__.py
|       |   |   |       
|       |   |   +---memory_inventory
|       |   |   |       cli.py
|       |   |   |       README.md
|       |   |   |       __init__.py
|       |   |   |       
|       |   |   +---merge_candidates
|       |   |   |       cli.py
|       |   |   |       README.md
|       |   |   |       __init__.py
|       |   |   |       
|       |   |   +---music_intermediates
|       |   |   |       cli.py
|       |   |   |       README.md
|       |   |   |       __init__.py
|       |   |   |       
|       |   |   +---rag_context
|       |   |   |       build_context_pack_cli.py
|       |   |   |       chunking.py
|       |   |   |       common.py
|       |   |   |       context_pack.py
|       |   |   |       embedding.py
|       |   |   |       index_status.py
|       |   |   |       ingest_repo_cli.py
|       |   |   |       query_context_cli.py
|       |   |   |       README.md
|       |   |   |       repo_files.py
|       |   |   |       retrieval.py
|       |   |   |       schema.py
|       |   |   |       store.py
|       |   |   |       unified_pack.py
|       |   |   |       __init__.py
|       |   |   |       
|       |   |   +---semantic_evidence_chunks
|       |   |   |   |   archive.py
|       |   |   |   |   chunker.py
|       |   |   |   |   cli.py
|       |   |   |   |   common.py
|       |   |   |   |   live_source.py
|       |   |   |   |   README.md
|       |   |   |   |   render.py
|       |   |   |   |   sections.py
|       |   |   |   |   summary.py
|       |   |   |   |   __init__.py
|       |   |   |   |   
|       |   |   |   \---select_code_chunks
|       |   |   |           cli.py
|       |   |   |           README.md
|       |   |   |           __init__.py
|       |   |   |           
|       |   |   +---shared_toolbox_bundle
|       |   |   |       cli.py
|       |   |   |       collection.py
|       |   |   |       common.py
|       |   |   |       provider_state.py
|       |   |   |       README.md
|       |   |   |       summary.py
|       |   |   |       tooling.py
|       |   |   |       __init__.py
|       |   |   |       
|       |   |   +---state_packet
|       |   |   |       cli.py
|       |   |   |       README.md
|       |   |   |       __init__.py
|       |   |   |       
|       |   |   \---transient_request_context
|       |   |           cli.py
|       |   |           README.md
|       |   |           __init__.py
|       |   |           
|       |   +---context_pack
|       |   |       README.md
|       |   |       __init__.py
|       |   |       
|       |   +---context_reload
|       |   |       README.md
|       |   |       __init__.py
|       |   |       
|       |   +---file_refs
|       |   |       README.md
|       |   |       __init__.py
|       |   |       
|       |   \---heap_context_memory_reload
|       |       |   builders.py
|       |       |   cli.py
|       |       |   common.py
|       |       |   delta.py
|       |       |   dynamic_gpu1_context.py
|       |       |   manifest.py
|       |       |   memory_write.py
|       |       |   rag_startup.py
|       |       |   README.md
|       |       |   runner.py
|       |       |   runner_state.py
|       |       |   scanner.py
|       |       |   startup_scan.py
|       |       |   task_docs.py
|       |       |   TOOL_CONTEXT.md
|       |       |   __init__.py
|       |       |   
|       |       \---reconcile_report
|       |               cli.py
|       |               README.md
|       |               __init__.py
|       |               
|       +---memory
|       |   |   flow.svg
|       |   |   README.md
|       |   |   __init__.py
|       |   |   
|       |   +---agent_memory
|       |   |   |   common.py
|       |   |   |   models.py
|       |   |   |   policy.py
|       |   |   |   README.md
|       |   |   |   routing_cli.py
|       |   |   |   routing_report.py
|       |   |   |   routing_requests.py
|       |   |   |   sqlite_cli.py
|       |   |   |   sqlite_report.py
|       |   |   |   sqlite_store.py
|       |   |   |   state.py
|       |   |   |   state_packet.py
|       |   |   |   storage.py
|       |   |   |   TOOL_CONTEXT.md
|       |   |   |   __init__.py
|       |   |   |   
|       |   |   \---review
|       |   |           cli.py
|       |   |           README.md
|       |   |           __init__.py
|       |   |           
|       |   +---fts5
|       |   |       README.md
|       |   |       __init__.py
|       |   |       
|       |   +---persistent
|       |   |       README.md
|       |   |       __init__.py
|       |   |       
|       |   +---pointers
|       |   |       README.md
|       |   |       __init__.py
|       |   |       
|       |   +---sqlite
|       |   |       README.md
|       |   |       __init__.py
|       |   |       
|       |   \---volatile
|       |           README.md
|       |           __init__.py
|       |           
|       \---pointers
|           |   README.md
|           |   __init__.py
|           |   
|           +---graph
|           |       README.md
|           |       __init__.py
|           |       
|           +---resume
|           |       README.md
|           |       __init__.py
|           |       
|           \---revision_context
|                   README.md
|                   __init__.py
|                   
+---commands
|       branch.json
|       diff_check.json
|       diff_name_status.json
|       diff_stat.json
|       status.json
|       
+---diag-qwen30b-20260607-133905
|       api-show.pretty.json
|       api-show.request.json
|       api-show.response.json
|       api-tags.response.json
|       api-version.response.json
|       native-generate-basic.request.json
|       native-generate-basic.response.json
|       native-generate-thinking-probe.request.json
|       native-generate-thinking-probe.response.json
|       ollama-list.txt
|       ollama-version.txt
|       v1-model-detail.response.json
|       v1-models.response.json
|       
+---docs
|       ISOLATED_LAUNCH_GUIDE.md
|       launcher_contract.md
|       OVMS_RERANKER_SETUP.md
|       runtime_env_contract.md
|       START_HERE_RUNTIME.md
|       
+---executor-runs
|       README.md
|       
+---indexAI
|   \---agent_memory
|           agent_memory.sqlite
|           agent_memory.sqlite-shm
|           agent_memory.sqlite-wal
|           
+---knowledge-bad-md
|       README.md
|       
+---knowledge-code-packs
|       README.md
|       
+---knowledge-md
|       README.md
|       
+---knowledge-md-parts
|       README.md
|       
+---knowledge-small-md
|       README.md
|       
+---knowledge-sync
|       README.md
|       
+---knowledge-tiny-md
|       README.md
|       
+---knowledge-upload-batches
|       README.md
|       
+---lab-patches
|       README.md
|       
+---lab-worktrees
|       README.md
|       
+---logs
|       README.md
|       
+---modelfiles
|       Modelfile.devstral-32k
|       Modelfile.Modelfile.qwen3task-8k
|       Modelfile.qwen3coder-32k
|       Modelfile.qwen3task-8k
|       README.md
|       
+---models-cpu
|       README.md
|       
+---models-ovms-rerank
|   |   config.json
|   |   README.md
|   |   
|   \---models
|       \---bge-reranker-v2-m3
|           |   .gitattributes
|           |   config.json
|           |   model.safetensors
|           |   openvino_config.json
|           |   openvino_detokenizer.bin
|           |   openvino_detokenizer.xml
|           |   openvino_model.bin
|           |   openvino_model.xml
|           |   openvino_tokenizer.bin
|           |   openvino_tokenizer.xml
|           |   README.md
|           |   sentencepiece.bpe.model
|           |   special_tokens_map.json
|           |   tokenizer.json
|           |   tokenizer_config.json
|           |   
|           +---.cache
|           |   \---huggingface
|           |       |   .gitignore
|           |       |   CACHEDIR.TAG
|           |       |   
|           |       +---download
|           |       |   |   .gitattributes.metadata
|           |       |   |   config.json.metadata
|           |       |   |   model.safetensors.metadata
|           |       |   |   README.md.metadata
|           |       |   |   sentencepiece.bpe.model.metadata
|           |       |   |   special_tokens_map.json.metadata
|           |       |   |   tokenizer.json.metadata
|           |       |   |   tokenizer_config.json.metadata
|           |       |   |   
|           |       |   \---assets
|           |       |           BEIR-bge-en-v1.5.png.metadata
|           |       |           BEIR-e5-mistral.png.metadata
|           |       |           CMTEB-retrieval-bge-zh-v1.5.png.metadata
|           |       |           llama-index.png.metadata
|           |       |           miracl-bge-m3.png.metadata
|           |       |           
|           |       \---trees
|           |               953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e.json
|           |               
|           \---assets
|                   BEIR-bge-en-v1.5.png
|                   BEIR-e5-mistral.png
|                   CMTEB-retrieval-bge-zh-v1.5.png
|                   llama-index.png
|                   miracl-bge-m3.png
|                   
+---models-task
|       README.md
|       
+---npu-models
|       README.md
|       
+---ollama-modelfiles
|       qwen36-35b-codex-lean.Modelfile
|       
+---openwebui-data
|       README.md
|       
+---output
|   +---agent-jobs
|   \---ai_runtime_memory
|           operational_context.sqlite
|           operational_context.sqlite-shm
|           operational_context.sqlite-wal
|           
+---ovms-runtime
|   |   README.md
|   |   setupvars.ps1
|   |   
|   \---bin
+---payloads
|       README.md
|       
+---project-openwebui-pipelines-controller
|   |   .env.example
|   |   docker-compose.pipelines.override.yml
|   |   README.md
|   |   
|   +---docs
|   |       CHAIN_OF_CAUSALITY.md
|   |       
|   \---pipelines
|           aicarmine_vulkan_controller_pipeline.py
|           
+---qwen-agent
|       README.md
|       
+---qwen-agent-workspace
|       README.md
|       
+---qwen-context
|       README.md
|       
+---reads
|       .clinerules__hooks__lib__aicarmine_cline_mcp_router.ps1.json
|       .clinerules__hooks__lib__aicarmine_cline_pretool_observer.ps1.json
|       .clinerules__hooks__PostToolUse.ps1.json
|       .clinerules__hooks__PreToolUse.ps1.json
|       .docs__tool_symbol_reference.json.json
|       cline_mcp_servers.json.json
|       models-ovms-rerank__README.md.json
|       README.md.json
|       services__aicarmine_broker__application__evidence__builder.py.json
|       services__aicarmine_broker__application__planner__loop.py.json
|       services__aicarmine_broker__application__prompt__tool_contract.py.json
|       services__codex_bridge__agentic_loop_client_mcp_server.py.json
|       services__codex_bridge__MCP_GUIDE.md.json
|       services__codex_bridge__mcp_server.py.json
|       services__model_export__cli.py.json
|       services__MODULE_TECHNICAL_DESCRIPTIONS.md.json
|       
+---services
|   |   aicarmine-executor-server.ps1
|   |   aicarmine-executor-server.py
|   |   aicarmine-jupyter-codeinterpreter.ps1
|   |   aicarmine-openwebui-serve.py
|   |   aicarmine-run-safe-command.ps1
|   |   aicarmine-vulkan-tool-broker.ps1
|   |   aicarmine_codex_mcp_server.py
|   |   aicarmine_codex_ollama_responses_bridge.py
|   |   aicarmine_vulkan_bridge_server.py
|   |   aicarmine_vulkan_tool_broker.py
|   |   apply_openwebui_ps1_open_terminal.py
|   |   check-dev-toolchain.ps1
|   |   CODEX_OPENWEBUI_PAYLOAD_LIMITATION.md
|   |   END_TO_END_AGENTIC_FLOW.md
|   |   export_model.py
|   |   flow.svg
|   |   MODULE_TECHNICAL_DESCRIPTIONS.md
|   |   npu-phi-service.ps1
|   |   ollama-task-vulkan.ps1
|   |   openvino-env.ps1
|   |   openwebui.ps1
|   |   OPENWEBUI_INLINE_EVIDENCE_CONTRACT.md
|   |   ovms-reranker-npu.ps1
|   |   README.md
|   |   requirements-agentic-optional.txt
|   |   RUNTIME_SCRIPT_REFERENCE.md
|   |   SERVICES_MODULE_TECHNICAL_REFERENCE.md
|   |   sync-lab-from-main.ps1
|   |   VALIDATOR_ONLY_AGENTIC_LOOP_CONTRACT.md
|   |   watch-lab-mirror.ps1
|   |   
|   +---aicarmine_broker
|   |   |   agent_entry.py
|   |   |   app.py
|   |   |   code_edit_proposal_contract.py
|   |   |   flow.svg
|   |   |   helper.py
|   |   |   job_html.py
|   |   |   job_html_assets.py
|   |   |   job_planner_lab.py
|   |   |   job_store.py
|   |   |   JOB_VIEW_OPTIMIZATION_NOTES.md
|   |   |   JOB_VIEW_OPTIMIZATION_NOTES.md.bak-20260617-182741
|   |   |   memory_tools.py
|   |   |   MODULE_REFERENCE.md
|   |   |   planner.py
|   |   |   planner_intrinsic_context.py
|   |   |   public_wrapper.py
|   |   |   README.md
|   |   |   repo_tools.py
|   |   |   test_planner_lab_js.py
|   |   |   tool_contract.py
|   |   |   tool_dispatch.py
|   |   |   tool_registry.py
|   |   |   tool_schemas.py
|   |   |   tool_selection.py
|   |   |   __init__.py
|   |   |   
|   |   +---application
|   |   |   |   __init__.py
|   |   |   |   
|   |   |   +---code_product
|   |   |   |   |   history.py
|   |   |   |   |   public_outputs.py
|   |   |   |   |   required_working_set.py
|   |   |   |   |   state.py
|   |   |   |   |   __init__.py
|   |   |   |   |   
|   |   |   |   \---__pycache__
|   |   |   |           history.cpython-314.pyc
|   |   |   |           public_outputs.cpython-314.pyc
|   |   |   |           required_working_set.cpython-314.pyc
|   |   |   |           state.cpython-314.pyc
|   |   |   |           __init__.cpython-314.pyc
|   |   |   |           
|   |   |   +---command
|   |   |   |   |   execution_policy.py
|   |   |   |   |   __init__.py
|   |   |   |   |   
|   |   |   |   \---__pycache__
|   |   |   |           execution_policy.cpython-314.pyc
|   |   |   |           __init__.cpython-314.pyc
|   |   |   |           
|   |   |   +---controller
|   |   |   |   |   diagnostics.py
|   |   |   |   |   guards.py
|   |   |   |   |   memory.py
|   |   |   |   |   orientation_lane.py
|   |   |   |   |   preseed.py
|   |   |   |   |   rag_preseed.py
|   |   |   |   |   __init__.py
|   |   |   |   |   
|   |   |   |   \---__pycache__
|   |   |   |           diagnostics.cpython-314.pyc
|   |   |   |           guards.cpython-314.pyc
|   |   |   |           memory.cpython-314.pyc
|   |   |   |           orientation_lane.cpython-314.pyc
|   |   |   |           preseed.cpython-314.pyc
|   |   |   |           rag_preseed.cpython-314.pyc
|   |   |   |           __init__.cpython-314.pyc
|   |   |   |           
|   |   |   +---evidence
|   |   |   |   |   audit_guidance.py
|   |   |   |   |   builder.py
|   |   |   |   |   core_discovery.py
|   |   |   |   |   coverage_scorer.py
|   |   |   |   |   execution_digest.py
|   |   |   |   |   final_quality.py
|   |   |   |   |   fix_builder_syntax.py
|   |   |   |   |   fix_builder_syntax_v2.py
|   |   |   |   |   goal_classifier.py
|   |   |   |   |   goal_scope.py
|   |   |   |   |   initial_orientation.py
|   |   |   |   |   repo_history.py
|   |   |   |   |   repo_path_policy.py
|   |   |   |   |   required_working_set.py
|   |   |   |   |   scope_conflict_resolution.py
|   |   |   |   |   user_scope_claims.py
|   |   |   |   |   __init__.py
|   |   |   |   |   
|   |   |   |   \---__pycache__
|   |   |   |           audit_guidance.cpython-314.pyc
|   |   |   |           builder.cpython-314.pyc
|   |   |   |           core_discovery.cpython-314.pyc
|   |   |   |           coverage_scorer.cpython-314.pyc
|   |   |   |           execution_digest.cpython-314.pyc
|   |   |   |           final_quality.cpython-314.pyc
|   |   |   |           goal_classifier.cpython-314.pyc
|   |   |   |           goal_scope.cpython-314.pyc
|   |   |   |           initial_orientation.cpython-314.pyc
|   |   |   |           repo_history.cpython-314.pyc
|   |   |   |           repo_path_policy.cpython-314.pyc
|   |   |   |           required_working_set.cpython-314.pyc
|   |   |   |           scope_conflict_resolution.cpython-314.pyc
|   |   |   |           user_scope_claims.cpython-314.pyc
|   |   |   |           __init__.cpython-314.pyc
|   |   |   |           
|   |   |   +---job
|   |   |   |   |   action_router.py
|   |   |   |   |   lifecycle.py
|   |   |   |   |   response_values.py
|   |   |   |   |   selector_runner.py
|   |   |   |   |   status_response.py
|   |   |   |   |   terminal_response.py
|   |   |   |   |   wait_response.py
|   |   |   |   |   worker.py
|   |   |   |   |   __init__.py
|   |   |   |   |   
|   |   |   |   \---__pycache__
|   |   |   |           action_router.cpython-314.pyc
|   |   |   |           lifecycle.cpython-314.pyc
|   |   |   |           response_values.cpython-314.pyc
|   |   |   |           selector_runner.cpython-314.pyc
|   |   |   |           status_response.cpython-314.pyc
|   |   |   |           terminal_response.cpython-314.pyc
|   |   |   |           wait_response.cpython-314.pyc
|   |   |   |           worker.cpython-314.pyc
|   |   |   |           __init__.cpython-314.pyc
|   |   |   |           
|   |   |   +---memory
|   |   |   |       conflict_detector.py
|   |   |   |       __init__.py
|   |   |   |       
|   |   |   +---npu_phi
|   |   |   |   |   client.py
|   |   |   |   |   policy.py
|   |   |   |   |   __init__.py
|   |   |   |   |   
|   |   |   |   \---__pycache__
|   |   |   |           client.cpython-314.pyc
|   |   |   |           policy.cpython-314.pyc
|   |   |   |           __init__.cpython-314.pyc
|   |   |   |           
|   |   |   +---planner
|   |   |   |   |   apply_patch_p1_validator.py
|   |   |   |   |   decision_normalizer.py
|   |   |   |   |   lane_catalog.py
|   |   |   |   |   loop.py
|   |   |   |   |   required_progress.py
|   |   |   |   |   state.py
|   |   |   |   |   status.py
|   |   |   |   |   system_prompt.py
|   |   |   |   |   turn.py
|   |   |   |   |   validation_rejections.py
|   |   |   |   |   validator.py
|   |   |   |   |   __init__.py
|   |   |   |   |   
|   |   |   |   \---__pycache__
|   |   |   |           decision_normalizer.cpython-314.pyc
|   |   |   |           lane_catalog.cpython-314.pyc
|   |   |   |           loop.cpython-314.pyc
|   |   |   |           required_progress.cpython-314.pyc
|   |   |   |           state.cpython-314.pyc
|   |   |   |           status.cpython-314.pyc
|   |   |   |           system_prompt.cpython-314.pyc
|   |   |   |           turn.cpython-314.pyc
|   |   |   |           validation_rejections.cpython-314.pyc
|   |   |   |           validator.cpython-314.pyc
|   |   |   |           __init__.cpython-314.pyc
|   |   |   |           
|   |   |   +---prompt
|   |   |   |   |   available_tools.py
|   |   |   |   |   budget.py
|   |   |   |   |   context_windows.py
|   |   |   |   |   evidence_contract.py
|   |   |   |   |   history_contract.py
|   |   |   |   |   history_messages.py
|   |   |   |   |   intrinsic_context.py
|   |   |   |   |   pack_builder.py
|   |   |   |   |   text_windows.py
|   |   |   |   |   tool_contract.py
|   |   |   |   |   values.py
|   |   |   |   |   window_signatures.py
|   |   |   |   |   __init__.py
|   |   |   |   |   
|   |   |   |   \---__pycache__
|   |   |   |           available_tools.cpython-314.pyc
|   |   |   |           budget.cpython-314.pyc
|   |   |   |           context_windows.cpython-314.pyc
|   |   |   |           evidence_contract.cpython-314.pyc
|   |   |   |           history_contract.cpython-314.pyc
|   |   |   |           history_messages.cpython-314.pyc
|   |   |   |           intrinsic_context.cpython-314.pyc
|   |   |   |           pack_builder.cpython-314.pyc
|   |   |   |           text_windows.cpython-314.pyc
|   |   |   |           tool_contract.cpython-314.pyc
|   |   |   |           values.cpython-314.pyc
|   |   |   |           window_signatures.cpython-314.pyc
|   |   |   |           __init__.cpython-314.pyc
|   |   |   |           
|   |   |   +---public_payload
|   |   |   |   |   evidence_materializer.py
|   |   |   |   |   field_names.py
|   |   |   |   |   final_state_result.py
|   |   |   |   |   history_ledger.py
|   |   |   |   |   openwebui_terminal_answer.py
|   |   |   |   |   openwebui_tool_context.py
|   |   |   |   |   payload_index_resolver.py
|   |   |   |   |   terminal_context_rows.py
|   |   |   |   |   terminal_result.py
|   |   |   |   |   terminal_sanitizer.py
|   |   |   |   |   tool_context.py
|   |   |   |   |   __init__.py
|   |   |   |   |   
|   |   |   |   +---lab
|   |   |   |   |   |   __init__.py
|   |   |   |   |   |   
|   |   |   |   |   \---__pycache__
|   |   |   |   |           __init__.cpython-314.pyc
|   |   |   |   |           
|   |   |   |   \---__pycache__
|   |   |   |           evidence_materializer.cpython-314.pyc
|   |   |   |           field_names.cpython-314.pyc
|   |   |   |           final_state_result.cpython-314.pyc
|   |   |   |           history_ledger.cpython-314.pyc
|   |   |   |           openwebui_terminal_answer.cpython-314.pyc
|   |   |   |           openwebui_tool_context.cpython-314.pyc
|   |   |   |           payload_index_resolver.cpython-314.pyc
|   |   |   |           terminal_context_rows.cpython-314.pyc
|   |   |   |           terminal_result.cpython-314.pyc
|   |   |   |           terminal_sanitizer.cpython-314.pyc
|   |   |   |           tool_context.cpython-314.pyc
|   |   |   |           __init__.cpython-314.pyc
|   |   |   |           
|   |   |   +---replay
|   |   |   |       loop_replay.py
|   |   |   |       __init__.py
|   |   |   |       
|   |   |   +---runtime_debug
|   |   |   |   |   debug_packet.py
|   |   |   |   |   __init__.py
|   |   |   |   |   
|   |   |   |   \---__pycache__
|   |   |   |           debug_packet.cpython-314.pyc
|   |   |   |           __init__.cpython-314.pyc
|   |   |   |           
|   |   |   +---search
|   |   |   |   |   search_quality.py
|   |   |   |   |   __init__.py
|   |   |   |   |   
|   |   |   |   \---__pycache__
|   |   |   |           search_quality.cpython-314.pyc
|   |   |   |           __init__.cpython-314.pyc
|   |   |   |           
|   |   |   +---shared
|   |   |   |   |   clean_values.py
|   |   |   |   |   diagnostics.py
|   |   |   |   |   evidence_contract_summary.py
|   |   |   |   |   history_ledger.py
|   |   |   |   |   history_queries.py
|   |   |   |   |   path_tokens.py
|   |   |   |   |   payload_metadata.py
|   |   |   |   |   __init__.py
|   |   |   |   |   
|   |   |   |   \---__pycache__
|   |   |   |           clean_values.cpython-314.pyc
|   |   |   |           diagnostics.cpython-314.pyc
|   |   |   |           evidence_contract_summary.cpython-314.pyc
|   |   |   |           history_ledger.cpython-314.pyc
|   |   |   |           history_queries.cpython-314.pyc
|   |   |   |           path_tokens.cpython-314.pyc
|   |   |   |           payload_metadata.cpython-314.pyc
|   |   |   |           __init__.cpython-314.pyc
|   |   |   |           
|   |   |   +---tool_surface
|   |   |   |   |   action_proof_ledger.py
|   |   |   |   |   batch_contract.py
|   |   |   |   |   candidate_actions.py
|   |   |   |   |   candidate_action_gate.py
|   |   |   |   |   dispatcher.py
|   |   |   |   |   manifest_builder.py
|   |   |   |   |   required_tool_call.py
|   |   |   |   |   result_compaction.py
|   |   |   |   |   result_digest.py
|   |   |   |   |   turn_surface_policy.py
|   |   |   |   |   __init__.py
|   |   |   |   |   
|   |   |   |   \---__pycache__
|   |   |   |           action_proof_ledger.cpython-314.pyc
|   |   |   |           batch_contract.cpython-314.pyc
|   |   |   |           candidate_actions.cpython-314.pyc
|   |   |   |           candidate_action_gate.cpython-314.pyc
|   |   |   |           dispatcher.cpython-314.pyc
|   |   |   |           manifest_builder.cpython-314.pyc
|   |   |   |           required_tool_call.cpython-314.pyc
|   |   |   |           result_compaction.cpython-314.pyc
|   |   |   |           result_digest.cpython-314.pyc
|   |   |   |           turn_surface_policy.cpython-314.pyc
|   |   |   |           __init__.cpython-314.pyc
|   |   |   |           
|   |   |   \---__pycache__
|   |   |           __init__.cpython-314.pyc
|   |   |           
|   |   +---config
|   |   |   |   compatibility.py
|   |   |   |   env_loader.py
|   |   |   |   models.py
|   |   |   |   __init__.py
|   |   |   |   
|   |   |   \---__pycache__
|   |   |           compatibility.cpython-314.pyc
|   |   |           env_loader.cpython-314.pyc
|   |   |           models.cpython-314.pyc
|   |   |           __init__.cpython-314.pyc
|   |   |           
|   |   +---contracts
|   |   |   |   command_runner.py
|   |   |   |   dispatcher.py
|   |   |   |   job_repository.py
|   |   |   |   planner_client.py
|   |   |   |   prompt_store.py
|   |   |   |   repo_filesystem.py
|   |   |   |   tool.py
|   |   |   |   validator.py
|   |   |   |   __init__.py
|   |   |   |   
|   |   |   \---__pycache__
|   |   |           command_runner.cpython-314.pyc
|   |   |           dispatcher.cpython-314.pyc
|   |   |           job_repository.cpython-314.pyc
|   |   |           planner_client.cpython-314.pyc
|   |   |           prompt_store.cpython-314.pyc
|   |   |           repo_filesystem.cpython-314.pyc
|   |   |           tool.cpython-314.pyc
|   |   |           validator.cpython-314.pyc
|   |   |           __init__.cpython-314.pyc
|   |   |           
|   |   +---domain
|   |   |   |   config.py
|   |   |   |   decisions.py
|   |   |   |   errors.py
|   |   |   |   evidence.py
|   |   |   |   job.py
|   |   |   |   models.py
|   |   |   |   results.py
|   |   |   |   tool.py
|   |   |   |   __init__.py
|   |   |   |   
|   |   |   \---__pycache__
|   |   |           models.cpython-314.pyc
|   |   |           __init__.cpython-314.pyc
|   |   |           
|   |   +---infrastructure
|   |   |   |   command_runner.py
|   |   |   |   executable_resolver.py
|   |   |   |   filesystem_repo.py
|   |   |   |   job_sqlite_store.py
|   |   |   |   job_store_repository.py
|   |   |   |   json_files.py
|   |   |   |   ollama_planner_client.py
|   |   |   |   result_compaction.py
|   |   |   |   time_provider.py
|   |   |   |   __init__.py
|   |   |   |   
|   |   |   \---__pycache__
|   |   |           command_runner.cpython-314.pyc
|   |   |           executable_resolver.cpython-314.pyc
|   |   |           filesystem_repo.cpython-314.pyc
|   |   |           job_sqlite_store.cpython-314.pyc
|   |   |           job_store_repository.cpython-314.pyc
|   |   |           json_files.cpython-314.pyc
|   |   |           ollama_planner_client.cpython-314.pyc
|   |   |           result_compaction.cpython-314.pyc
|   |   |           time_provider.cpython-314.pyc
|   |   |           __init__.cpython-314.pyc
|   |   |           
|   |   +---planner_core
|   |   |   |   cache.py
|   |   |   |   json_io.py
|   |   |   |   README.md
|   |   |   |   __init__.py
|   |   |   |   
|   |   |   \---__pycache__
|   |   |           cache.cpython-314.pyc
|   |   |           json_io.cpython-314.pyc
|   |   |           __init__.cpython-314.pyc
|   |   |           
|   |   +---tools
|   |   |   |   command_safety.py
|   |   |   |   deterministic_common.py
|   |   |   |   git_surface.py
|   |   |   |   powershell_runner.py
|   |   |   |   repo_code_product.py
|   |   |   |   repo_command.py
|   |   |   |   repo_deterministic.py
|   |   |   |   repo_list_files.py
|   |   |   |   repo_patch.py
|   |   |   |   repo_read.py
|   |   |   |   repo_search.py
|   |   |   |   repo_semantic_search.py
|   |   |   |   repo_status.py
|   |   |   |   repo_tree.py
|   |   |   |   repo_validate.py
|   |   |   |   terminal.py
|   |   |   |   __init__.py
|   |   |   |   
|   |   |   \---__pycache__
|   |   |           command_safety.cpython-314.pyc
|   |   |           deterministic_common.cpython-314.pyc
|   |   |           git_surface.cpython-314.pyc
|   |   |           powershell_runner.cpython-314.pyc
|   |   |           repo_code_product.cpython-314.pyc
|   |   |           repo_command.cpython-314.pyc
|   |   |           repo_deterministic.cpython-314.pyc
|   |   |           repo_list_files.cpython-314.pyc
|   |   |           repo_patch.cpython-314.pyc
|   |   |           repo_read.cpython-314.pyc
|   |   |           repo_search.cpython-314.pyc
|   |   |           repo_semantic_search.cpython-314.pyc
|   |   |           repo_status.cpython-314.pyc
|   |   |           repo_tree.cpython-314.pyc
|   |   |           repo_validate.cpython-314.pyc
|   |   |           terminal.cpython-314.pyc
|   |   |           __init__.cpython-314.pyc
|   |   |           
|   |   \---__pycache__
|   |           agent_entry.cpython-314.pyc
|   |           app.cpython-314.pyc
|   |           code_edit_proposal_contract.cpython-314.pyc
|   |           helper.cpython-314.pyc
|   |           job_html.cpython-314.pyc
|   |           job_html_assets.cpython-314.pyc
|   |           job_planner_lab.cpython-314.pyc
|   |           job_store.cpython-314.pyc
|   |           memory_tools.cpython-314.pyc
|   |           planner.cpython-314.pyc
|   |           planner_intrinsic_context.cpython-314.pyc
|   |           public_wrapper.cpython-314.pyc
|   |           repo_tools.cpython-314.pyc
|   |           tool_contract.cpython-314.pyc
|   |           tool_dispatch.cpython-314.pyc
|   |           tool_registry.cpython-314.pyc
|   |           tool_schemas.cpython-314.pyc
|   |           tool_selection.cpython-314.pyc
|   |           __init__.cpython-314.pyc
|   |           
|   +---codex_bridge
|   |   |   agentic_loop_client_mcp_server.py
|   |   |   flow.svg
|   |   |   git_readonly_mcp_server.py
|   |   |   job_artifact_mcp_server.py
|   |   |   job_view_mcp_server.py
|   |   |   jsonrpc.py
|   |   |   local_subagent_mcp_server.py
|   |   |   MCP_GUIDE.md
|   |   |   mcp_server.py
|   |   |   MODULE_REFERENCE.md
|   |   |   ollama_responses_bridge.py
|   |   |   ops_mcp_server.py
|   |   |   ovms_alternative_reranker.py
|   |   |   project_memory_mcp_server.py
|   |   |   rag_index_repo.py
|   |   |   rag_mcp_server.py
|   |   |   README.md
|   |   |   repo_code_change_set.py
|   |   |   repo_code_mcp_server.py
|   |   |   repo_mcp_common.py
|   |   |   REPO_MCP_CONTRACT.md
|   |   |   repo_probe_profiles.py
|   |   |   repo_search_det_mcp_server.py
|   |   |   repo_state_mcp_server.py
|   |   |   repo_validate_mcp_server.py
|   |   |   responses_proxy.py
|   |   |   sqlite_readonly_mcp_server.py
|   |   |   start_reranker.ps1
|   |   |   storage.py
|   |   |   test_repo_code_mcp_serialization.py
|   |   |   tool_surface_cache.py
|   |   |   __init__.py
|   |   |   
|   |   \---__pycache__
|   |           agentic_loop_client_mcp_server.cpython-314.pyc
|   |           git_readonly_mcp_server.cpython-314.pyc
|   |           job_artifact_mcp_server.cpython-314.pyc
|   |           job_view_mcp_server.cpython-314.pyc
|   |           local_subagent_mcp_server.cpython-314.pyc
|   |           mcp_server.cpython-314.pyc
|   |           ops_mcp_server.cpython-314.pyc
|   |           project_memory_mcp_server.cpython-314.pyc
|   |           rag_index_repo.cpython-314.pyc
|   |           rag_mcp_server.cpython-314.pyc
|   |           repo_code_change_set.cpython-314.pyc
|   |           repo_code_mcp_server.cpython-314.pyc
|   |           repo_mcp_common.cpython-314.pyc
|   |           repo_probe_profiles.cpython-314.pyc
|   |           repo_search_det_mcp_server.cpython-314.pyc
|   |           repo_state_mcp_server.cpython-314.pyc
|   |           repo_validate_mcp_server.cpython-314.pyc
|   |           sqlite_readonly_mcp_server.cpython-314.pyc
|   |           
|   +---launch
|   |   |   env.ps1
|   |   |   flow.svg
|   |   |   http.ps1
|   |   |   MODULE_REFERENCE.md
|   |   |   ollama.ps1
|   |   |   openwebui_runtime.ps1
|   |   |   process.ps1
|   |   |   README.md
|   |   |   
|   |   \---contracts
|   |           env_contract.json
|   |           launch_order.md
|   |           ports_contract.json
|   |           
|   +---model_export
|   |       cli.py
|   |       config.py
|   |       exporters.py
|   |       flow.svg
|   |       MODULE_REFERENCE.md
|   |       README.md
|   |       __init__.py
|   |       
|   +---npu_phi_service
|   |       app.py
|   |       blob_lock.py
|   |       circuit_breaker.py
|   |       diagnostics.py
|   |       job_queue.py
|   |       MODULE_REFERENCE.md
|   |       pipeline.py
|   |       schemas.py
|   |       settings.py
|   |       __init__.py
|   |       __main__.py
|   |       
|   +---openwebui-data
|   |       README.md
|   |       
|   \---vulkan_bridge
|       |   agentic_v9.py
|       |   app.py
|       |   app_refactored.py
|       |   client.py
|       |   compact.py
|       |   config.py
|       |   flow.svg
|       |   MODULE_REFERENCE.md
|       |   openapi_builder.py
|       |   README.md
|       |   __init__.py
|       |   
|       \---application
|           |   materialization_report.py
|           |   payload_index_resolver.py
|           |   public_field_names.py
|           |   public_payload_linter.py
|           |   request_payload.py
|           |   response_values.py
|           |   __init__.py
|           |   
|           \---modules
|                   environment_utils.py
|                   request_utils.py
|                   
+---state
|   |   README.md
|   |   
|   +---codex_bridge
|   |   \---agentic_loop_client
|   |           reranker-3550.log
|   |           
|   +---codex_rag
|   |       code_rag.sqlite3
|   |       code_rag.sqlite3-shm
|   |       code_rag.sqlite3-wal
|   |       
|   \---project_memory
|           project_memory.sqlite3
|           
+---tool-results
|       1785415050-repo_status.json
|       1785416429-repo_fd_files.json
|       1785416449-repo_rg_search.json
|       1785416596-repo_read.json
|       1785416738-repo_propose_code_edit.json
|       1785416991-repo_validate.json
|       1785427917-repo_tree.json
|       1785427930-repo_list_files.json
|       1785427943-repo_list_files.json
|       1785427953-repo_read.json
|       1785427965-repo_read.json
|       1785427976-repo_read.json
|       1785427987-repo_read.json
|       1785427999-repo_read.json
|       1785428010-repo_read.json
|       1785428021-repo_read.json
|       1785428032-repo_read.json
|       1785428043-repo_read.json
|       1785428055-repo_read.json
|       1785428067-repo_read.json
|       1785428634-repo_read.json
|       1785428700-repo_read.json
|       1785428849-repo_read.json
|       1785428871-repo_search.json
|       1785428892-repo_fd_files.json
|       1785428907-repo_list_files.json
|       1785429042-repo_list_files.json
|       1785429330-repo_read.json
|       1785429349-repo_search.json
|       1785429368-repo_fd_files.json
|       1785429386-repo_rg_search.json
|       1785429409-repo_read.json
|       1785429428-repo_rg_search.json
|       1785429447-repo_rg_search.json
|       1785429466-repo_read.json
|       1785429485-repo_fd_files.json
|       1785429496-repo_fd_files.json
|       1785433569-repo_rg_search.json
|       1785433719-repo_rg_search.json
|       1785435726-repo_rg_search.json
|       1785435746-repo_rg_search.json
|       1785435893-repo_rg_search.json
|       1785436192-repo_read.json
|       
+---tools
|       generate_symbol_reference.py
|       mechanical_payload_surface_cut.py
|       mechanical_runtime_prune.py
|       mechanical_services_dedupe.py
|       symbol_resolution_assistant.py
|       
\---venvs
        README.md
        
