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
- function `repo_semantic_memory.cli.build_parser` src/repo_semantic_memory/cli.py:50-377
- function `repo_semantic_memory.cli._format_version_output` src/repo_semantic_memory/cli.py:380-386
- function `repo_semantic_memory.cli.main` src/repo_semantic_memory/cli.py:389-490
- function `repo_semantic_memory.cli._format_scan_table` src/repo_semantic_memory/cli.py:493-502
- function `repo_semantic_memory.cli._format_index_python_summary` src/repo_semantic_memory/cli.py:505-506
- function `repo_semantic_memory.cli._run_index_command` src/repo_semantic_memory/cli.py:509-573
- function `repo_semantic_memory.cli._run_git_summary_command` src/repo_semantic_memory/cli.py:576-593
- function `repo_semantic_memory.cli._run_inspect_entities_command` src/repo_semantic_memory/cli.py:596-608
- function `repo_semantic_memory.cli._run_inspect_relations_command` src/repo_semantic_memory/cli.py:611-623
- function `repo_semantic_memory.cli._run_repo_map_command` src/repo_semantic_memory/cli.py:626-641
- function `repo_semantic_memory.cli._run_eval_retrieval_command` src/repo_semantic_memory/cli.py:644-664
- function `repo_semantic_memory.cli._run_eval_compare_command` src/repo_semantic_memory/cli.py:667-692
- function `repo_semantic_memory.cli._run_pack_command` src/repo_semantic_memory/cli.py:695-726
- function `repo_semantic_memory.cli._run_components_infer_command` src/repo_semantic_memory/cli.py:729-736
- function `repo_semantic_memory.cli._run_components_list_command` src/repo_semantic_memory/cli.py:739-741
- function `repo_semantic_memory.cli._run_invariants_export_command` src/repo_semantic_memory/cli.py:744-752
- function `repo_semantic_memory.cli._run_invariants_import_command` src/repo_semantic_memory/cli.py:755-763
- function `repo_semantic_memory.cli._run_export_ai_command` src/repo_semantic_memory/cli.py:766-799
- function `repo_semantic_memory.cli._run_export_jsonl_command` src/repo_semantic_memory/cli.py:802-823
- function `repo_semantic_memory.cli._run_import_jsonl_command` src/repo_semantic_memory/cli.py:826-842
- function `repo_semantic_memory.cli._index_for_repo_map` src/repo_semantic_memory/cli.py:845-854
- function `repo_semantic_memory.cli._load_index_from_db` src/repo_semantic_memory/cli.py:857-865
- function `repo_semantic_memory.cli._merge_entities` src/repo_semantic_memory/cli.py:868-872
- function `repo_semantic_memory.cli._drop_python_module_file_entities` src/repo_semantic_memory/cli.py:875-880
- function `repo_semantic_memory.cli._format_relations_table` src/repo_semantic_memory/cli.py:883-897
- function `repo_semantic_memory.cli._format_components_table` src/repo_semantic_memory/cli.py:900-916

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
- `repo_semantic_memory.context.compression.available_profile_names`
- `repo_semantic_memory.context.compression.resolve_profile`

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
- `repo_semantic_memory.context.compression.CompressionProfile`
- `repo_semantic_memory.context.compression.available_profile_names`
- `repo_semantic_memory.context.compression.resolve_profile`
- `repo_semantic_memory.context.context_pack.ContextPack`
- `repo_semantic_memory.context.pack_builder.build_context_pack`
- `repo_semantic_memory.context.render_markdown.render_context_pack_markdown`
- `repo_semantic_memory.context.repo_map.build_repo_map_markdown`

## src/repo_semantic_memory/context/bm25.py
- module `repo_semantic_memory.context.bm25` src/repo_semantic_memory/context/bm25.py:1
- class `repo_semantic_memory.context.bm25.BM25Config` src/repo_semantic_memory/context/bm25.py:31-51
  - method `__post_init__` src/repo_semantic_memory/context/bm25.py:40-51
- class `repo_semantic_memory.context.bm25.FieldedDocument` src/repo_semantic_memory/context/bm25.py:55-59
- class `repo_semantic_memory.context.bm25.BM25Score` src/repo_semantic_memory/context/bm25.py:63-68
- class `repo_semantic_memory.context.bm25.FieldedBM25Index` src/repo_semantic_memory/context/bm25.py:71-160
  - method `__init__` src/repo_semantic_memory/context/bm25.py:74-111
  - method `config` src/repo_semantic_memory/context/bm25.py:114-115
  - method `score` src/repo_semantic_memory/context/bm25.py:117-160
- function `repo_semantic_memory.context.bm25.tokenize_text` src/repo_semantic_memory/context/bm25.py:163-174
- function `repo_semantic_memory.context.bm25._add_token` src/repo_semantic_memory/context/bm25.py:177-179

Static imports (unresolved):
- `__future__.annotations`
- `collections.Counter`
- `collections.abc.Mapping`
- `collections.abc.Sequence`
- `dataclasses.dataclass`
- `dataclasses.field`
- `math`
- `re`
- `types.MappingProxyType`

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

## src/repo_semantic_memory/context/compression.py
- module `repo_semantic_memory.context.compression` src/repo_semantic_memory/context/compression.py:1
- class `repo_semantic_memory.context.compression.CompressionProfile` src/repo_semantic_memory/context/compression.py:53-66
- function `repo_semantic_memory.context.compression.available_profile_names` src/repo_semantic_memory/context/compression.py:151-160
- function `repo_semantic_memory.context.compression.resolve_profile` src/repo_semantic_memory/context/compression.py:163-172
- function `repo_semantic_memory.context.compression.filter_related_relations` src/repo_semantic_memory/context/compression.py:175-191
- function `repo_semantic_memory.context.compression.filter_uncertainties` src/repo_semantic_memory/context/compression.py:194-200
- function `repo_semantic_memory.context.compression.filter_source_citations` src/repo_semantic_memory/context/compression.py:203-209
- function `repo_semantic_memory.context.compression.filter_semantic_components` src/repo_semantic_memory/context/compression.py:212-237
- function `repo_semantic_memory.context.compression.trim_import_names` src/repo_semantic_memory/context/compression.py:240-246

Static imports (unresolved):
- `__future__.annotations`
- `collections.abc.Sequence`
- `collections.defaultdict`
- `dataclasses.dataclass`
- `repo_semantic_memory.context.context_pack.SourceCitation`
- `repo_semantic_memory.memory.CompactSemanticComponent`

## .ai/context_policy.md