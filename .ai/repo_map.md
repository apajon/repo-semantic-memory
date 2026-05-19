# Repo map

## src/repo_semantic_memory/__init__.py
- module `repo_semantic_memory` src/repo_semantic_memory/__init__.py:1

Static imports (unresolved):
- `repo_semantic_memory.version.CONTEXT_PACK_VERSION`
- `repo_semantic_memory.version.PACKAGE_VERSION`
- `repo_semantic_memory.version.SCHEMA_VERSION`
- `repo_semantic_memory.version.VersionInfo`
- `repo_semantic_memory.version.get_version_info`

## src/repo_semantic_memory/cli.py
- module `repo_semantic_memory.cli` src/repo_semantic_memory/cli.py:1
- function `repo_semantic_memory.cli.build_parser` src/repo_semantic_memory/cli.py:46-356
- function `repo_semantic_memory.cli._format_version_output` src/repo_semantic_memory/cli.py:359-365
- function `repo_semantic_memory.cli.main` src/repo_semantic_memory/cli.py:368-459
- function `repo_semantic_memory.cli._format_scan_table` src/repo_semantic_memory/cli.py:462-471
- function `repo_semantic_memory.cli._format_index_python_summary` src/repo_semantic_memory/cli.py:474-475
- function `repo_semantic_memory.cli._run_index_command` src/repo_semantic_memory/cli.py:478-523
- function `repo_semantic_memory.cli._run_git_summary_command` src/repo_semantic_memory/cli.py:526-543
- function `repo_semantic_memory.cli._run_inspect_entities_command` src/repo_semantic_memory/cli.py:546-558
- function `repo_semantic_memory.cli._run_inspect_relations_command` src/repo_semantic_memory/cli.py:561-573
- function `repo_semantic_memory.cli._run_repo_map_command` src/repo_semantic_memory/cli.py:576-591
- function `repo_semantic_memory.cli._run_eval_retrieval_command` src/repo_semantic_memory/cli.py:594-614
- function `repo_semantic_memory.cli._run_eval_compare_command` src/repo_semantic_memory/cli.py:617-642
- function `repo_semantic_memory.cli._run_pack_command` src/repo_semantic_memory/cli.py:645-664
- function `repo_semantic_memory.cli._run_components_infer_command` src/repo_semantic_memory/cli.py:667-674
- function `repo_semantic_memory.cli._run_components_list_command` src/repo_semantic_memory/cli.py:677-679
- function `repo_semantic_memory.cli._run_invariants_export_command` src/repo_semantic_memory/cli.py:682-690
- function `repo_semantic_memory.cli._run_invariants_import_command` src/repo_semantic_memory/cli.py:693-701
- function `repo_semantic_memory.cli._run_export_ai_command` src/repo_semantic_memory/cli.py:704-737
- function `repo_semantic_memory.cli._run_export_jsonl_command` src/repo_semantic_memory/cli.py:740-761
- function `repo_semantic_memory.cli._run_import_jsonl_command` src/repo_semantic_memory/cli.py:764-780
- function `repo_semantic_memory.cli._index_for_repo_map` src/repo_semantic_memory/cli.py:783-789
- function `repo_semantic_memory.cli._load_index_from_db` src/repo_semantic_memory/cli.py:792-800
- function `repo_semantic_memory.cli._merge_entities` src/repo_semantic_memory/cli.py:803-807
- function `repo_semantic_memory.cli._drop_python_module_file_entities` src/repo_semantic_memory/cli.py:810-815
- function `repo_semantic_memory.cli._format_relations_table` src/repo_semantic_memory/cli.py:818-832
- function `repo_semantic_memory.cli._format_components_table` src/repo_semantic_memory/cli.py:835-851

Static imports (unresolved):
- `__future__.annotations`
- `argparse`
- `collections.abc.Sequence`
- `datetime.UTC`
- `datetime.datetime`
- `json`
- `pathlib.Path`
- `repo_semantic_memory.config.DEFAULT_CONFIG`
- `repo_semantic_memory.context.build_context_pack`
- `repo_semantic_memory.context.build_repo_map_markdown`
- `repo_semantic_memory.context.render_context_pack_markdown`
- `repo_semantic_memory.eval.render_compact_table`
- `repo_semantic_memory.eval.render_compare_compact_table`
- `repo_semantic_memory.eval.run_baseline_comparison`
- `repo_semantic_memory.eval.run_retrieval_benchmark`
- `repo_semantic_memory.eval.to_compare_json_payload`
- `repo_semantic_memory.eval.to_json_payload`
- `repo_semantic_memory.eval.write_compare_markdown_report`
- `repo_semantic_memory.eval.write_markdown_report`
- `repo_semantic_memory.exporters.AiDirectoryExporter`
- `repo_semantic_memory.exporters.export_jsonl_directory`
- `repo_semantic_memory.extractors.extract_filesystem_entities`
- `repo_semantic_memory.extractors.get_git_repository_summary`
- `repo_semantic_memory.extractors.index_python_path`
- `repo_semantic_memory.importers.import_jsonl_directory`
- `repo_semantic_memory.memory.attach_git_metadata_to_entities`
- `repo_semantic_memory.memory.export_invariants_yaml`
- `repo_semantic_memory.memory.import_invariants_yaml`
- `repo_semantic_memory.memory.infer_semantic_components`
- `repo_semantic_memory.model.Entity`
- `repo_semantic_memory.model.Relation`
- `repo_semantic_memory.model.SemanticComponent`
- `repo_semantic_memory.store.SQLiteStore`
- `repo_semantic_memory.store.build_default_extraction_metadata`
- `repo_semantic_memory.version.get_version_info`
- `sys`

## src/repo_semantic_memory/config.py
- module `repo_semantic_memory.config` src/repo_semantic_memory/config.py:1
- class `repo_semantic_memory.config.AppConfig` src/repo_semantic_memory/config.py:9-13

Static imports (unresolved):
- `__future__.annotations`
- `dataclasses.dataclass`

## src/repo_semantic_memory/context/__init__.py
- module `repo_semantic_memory.context` src/repo_semantic_memory/context/__init__.py:1

Static imports (unresolved):
- `repo_semantic_memory.context.budget.CharacterBudget`
- `repo_semantic_memory.context.context_pack.ContextPack`
- `repo_semantic_memory.context.pack_builder.build_context_pack`
- `repo_semantic_memory.context.render_markdown.render_context_pack_markdown`
- `repo_semantic_memory.context.repo_map.build_repo_map_markdown`

## src/repo_semantic_memory/context/budget.py
- module `repo_semantic_memory.context.budget` src/repo_semantic_memory/context/budget.py:1
- class `repo_semantic_memory.context.budget.CharacterBudget` src/repo_semantic_memory/context/budget.py:9-37
  - method `__post_init__` src/repo_semantic_memory/context/budget.py:16-18
  - method `append_line` src/repo_semantic_memory/context/budget.py:20-29
  - method `append_truncation_notice` src/repo_semantic_memory/context/budget.py:31-33
  - method `render` src/repo_semantic_memory/context/budget.py:35-37

Static imports (unresolved):
- `__future__.annotations`
- `dataclasses.dataclass`
- `dataclasses.field`

## src/repo_semantic_memory/context/context_pack.py
- module `repo_semantic_memory.context.context_pack` src/repo_semantic_memory/context/context_pack.py:1
- class `repo_semantic_memory.context.context_pack.SourceCitation` src/repo_semantic_memory/context/context_pack.py:14-41
  - method `to_dict` src/repo_semantic_memory/context/context_pack.py:26-41
- class `repo_semantic_memory.context.context_pack.ContextPack` src/repo_semantic_memory/context/context_pack.py:45-93
  - method `__post_init__` src/repo_semantic_memory/context/context_pack.py:60-62
  - method `to_dict` src/repo_semantic_memory/context/context_pack.py:64-86
  - method `to_yaml` src/repo_semantic_memory/context/context_pack.py:88-93
- function `repo_semantic_memory.context.context_pack.relation_key` src/repo_semantic_memory/context/context_pack.py:96-103
- function `repo_semantic_memory.context.context_pack._entity_payload` src/repo_semantic_memory/context/context_pack.py:106-120
- function `repo_semantic_memory.context.context_pack._relation_payload` src/repo_semantic_memory/context/context_pack.py:123-132

Static imports (unresolved):
- `__future__.annotations`
- `dataclasses.dataclass`
- `json`
- `repo_semantic_memory.memory.CompactSemanticComponent`
- `repo_semantic_memory.model.Entity`
- `repo_semantic_memory.model.Relation`
- `repo_semantic_memory.version.get_version_info`

## src/repo_semantic_memory/context/pack_builder.py
- module `repo_semantic_memory.context.pack_builder` src/repo_semantic_memory/context/pack_builder.py:1
- function `repo_semantic_memory.context.pack_builder.build_context_pack` src/repo_semantic_memory/context/pack_builder.py:81-221
[truncated: budget reached]