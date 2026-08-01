import os, glob, re

os.chdir('C:/Users/sanit/agentic-tool-loop/services')
files = glob.glob('aicarmine_broker/**/*.py', recursive=True)
count = 0
fixed_files = []
for f in files:
    if not os.path.isfile(f) or not f.endswith('.py'):
        continue
    with open(f, 'r', encoding='utf-8') as fh:
        content = fh.read()
    original = content
    # Fix broken except Exception as _e: followed by raise BrokerError( on next line
    # Pattern: except Exception as _e:\n        raise BrokerError(\n            except Exception as exc:\n        raise BrokerError(
        content = content.replace('services.aicarmine_broker.error_handling', 'aicarmine_broker.error_handling')
        count += 1
    # Fix broken import paths: services.aicarmine_broker.application -> aicarmine_broker.application
    if 'services.aicarmine_broker.application' in content:
        content = content.replace('services.aicarmine_broker.application', 'aicarmine_broker.application')
        count += 1
    # Fix broken import paths: services.aicarmine_broker.infrastructure -> aicarmine_broker.infrastructure
    if 'services.aicarmine_broker.infrastructure' in content:
        content = content.replace('services.aicarmine_broker.infrastructure', 'aicarmine_broker.infrastructure')
        count += 1
    # Fix broken import paths: services.aicarmine_broker.prompt -> aicarmine_broker.prompt
    if 'services.aicarmine_broker.prompt' in content:
        content = content.replace('services.aicarmine_broker.prompt', 'aicarmine_broker.prompt')
        count += 1
    # Fix broken import paths: services.aicarmine_broker.contracts -> aicarmine_broker.contracts
    if 'services.aicarmine_broker.contracts' in content:
        content = content.replace('services.aicarmine_broker.contracts', 'aicarmine_broker.contracts')
        count += 1
    # Fix broken import paths: services.aicarmine_broker.tool_surface -> aicarmine_broker.tool_surface
    if 'services.aicarmine_broker.tool_surface' in content:
        content = content.replace('services.aicarmine_broker.tool_surface', 'aicarmine_broker.tool_surface')
        count += 1
    # Fix broken import paths: services.aicarmine_broker.domain -> aicarmine_broker.domain
    if 'services.aicarmine_broker.domain' in content:
        content = content.replace('services.aicarmine_broker.domain', 'aicarmine_broker.domain')
        count += 1
    # Fix broken import paths: services.aicarmine_broker.code_product -> aicarmine_broker.code_product
    if 'services.aicarmine_broker.code_product' in content:
        content = content.replace('services.aicarmine_broker.code_product', 'aicarmine_broker.code_product')
        count += 1
    # Fix broken import paths: services.aicarmine_broker.controller -> aicarmine_broker.controller
    if 'services.aicarmine_broker.controller' in content:
        content = content.replace('services.aicarmine_broker.controller', 'aicarmine_broker.controller')
        count += 1
    # Fix broken import paths: services.aicarmine_broker.planner_core -> aicarmine_broker.planner_core
    if 'services.aicarmine_broker.planner_core' in content:
        content = content.replace('services.aicarmine_broker.planner_core', 'aicarmine_broker.planner_core')
        count += 1
    # Fix broken import paths: services.aicarmine_broker.tools -> aicarmine_broker.tools
    if 'services.aicarmine_broker.tools' in content:
        content = content.replace('services.aicarmine_broker.tools', 'aicarmine_broker.tools')
        count += 1
    # Fix broken import paths: services.aicarmine_broker.npu_phi -> aicarmine_broker.npu_phi
    if 'services.aicarmine_broker.npu_phi' in content:
        content = content.replace('services.aicarmine_broker.npu_phi', 'aicarmine_broker.npu_phi')
        count += 1
    # Fix broken import paths: services.aicarmine_broker.replay -> aicarmine_broker.replay
    if 'services.aicarmine_broker.replay' in content:
        content = content.replace('services.aicarmine_broker.replay', 'aicarmine_broker.replay')
        count += 1
    # Fix broken import paths: services.aicarmine_broker.runtime_debug -> aicarmine_broker.runtime_debug
    if 'services.aicarmine_broker.runtime_debug' in content:
        content = content.replace('services.aicarmine_broker.runtime_debug', 'aicarmine_broker.runtime_debug')
        count += 1
    # Fix broken import paths: services.aicarmine_broker.search -> aicarmine_broker.search
    if 'services.aicarmine_broker.search' in content:
        content = content.replace('services.aicarmine_broker.search', 'aicarmine_broker.search')
        count += 1
    # Fix broken import paths: services.aicarmine_broker.command -> aicarmine_broker.command
    if 'services.aicarmine_broker.command' in content:
        content = content.replace('services.aicarmine_broker.command', 'aicarmine_broker.command')
        count += 1
    # Fix broken import paths: services.aicarmine_broker.helper -> aicarmine_broker.helper
    if 'services.aicarmine_broker.helper' in content:
        content = content.replace('services.aicarmine_broker.helper', 'aicarmine_broker.helper')
        count += 1
    # Fix broken import paths: services.aicarmine_broker.job_html -> aicarmine_broker.job_html
    if 'services.aicarmine_broker.job_html' in content:
        content = content.replace('services.aicarmine_broker.job_html', 'aicarmine_broker.job_html')
        count += 1
    # Fix broken import paths: services.aicarmine_broker.memory_tools -> aicarmine_broker.memory_tools
    if 'services.aicarmine_broker.memory_tools' in content:
        content = content.replace('services.aicarmine_broker.memory_tools', 'aicarmine_broker.memory_tools')
        count += 1
    # Fix broken import paths: services.aicarmine_broker.tool_contract -> aicarmine_broker.tool_contract
    if 'services.aicarmine_broker.tool_contract' in content:
        content = content.replace('services.aicarmine_broker.tool_contract', 'aicarmine_broker.tool_contract')
        count += 1
    # Fix broken import paths: services.aicarmine_broker.code_edit_proposal_contract -> aicarmine_broker.code_edit_proposal_contract
    if 'services.aicarmine_broker.code_edit_proposal_contract' in content:
        content = content.replace('services.aicarmine_broker.code_edit_proposal_contract', 'aicarmine_broker.code_edit_proposal_contract')
        count += 1
    if content != original:
        with open(f, 'w', encoding='utf-8') as fh:
            fh.write(content)
        fixed_files.append(f)
print(f'Done. Fixed {count} patterns in {len(fixed_files)} files.')
for ff in fixed_files:
    print(f'  - {ff}')