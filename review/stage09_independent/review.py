"""Independent read-only Stage 9 review. Outputs closed aggregate diagnostics only.

Never invoke a materializer; input paths are exact DEVELOPMENT/public constants.
Candidate helpers are reused for published hash formats and existing validators;
independent SQL and Python oracles separately test scheduling and Q04 semantics.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
from collections import Counter
from itertools import zip_longest

from safe_geocoding_pipeline.execution_policy import require_goethe_nhr_slurm
from safe_geocoding_pipeline.preprocessing.stages import s09_reference_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s09_reference_io as io
from safe_geocoding_pipeline.preprocessing.stages import s09_reference_pack as p
from safe_geocoding_pipeline.preprocessing.stages import s09_reference_input as upstream
from safe_geocoding_pipeline.preprocessing.stages import s09_reference_index as idx
from safe_geocoding_pipeline.preprocessing.stages import s09_reference_materializer as m
from safe_geocoding_pipeline.preprocessing.stages import s09_reference_validation as v
from safe_geocoding_pipeline.preprocessing.stages import s09_reference_coverage as cov

EXE = '3e10ac7c1309c2636f35c0709fa283305d60d998'
MANIFEST = '321c9d8352fac5b78612a7c8e52f6f810f92bddb1e91f7cfe348398a6d707240'
PUBLIC = 'dd7994b907250d515470b820bcbf42993a08e4f3116409b7c94168446e1c064a'
LOGICAL = '7ae84e149f4c9c2de7a791c9b326b88e387a70d155d8be55acf6b55e06bafae3'
EXPECTED_COUNTS = dict(zip(c.RELATIONS, (3, 47578, 1844460, 6565329, 626110, 48479)))
REPORT: dict = {'executable': EXE, 'checks': {}, 'diagnostics': {}, 'phases': []}
OUT: Path
START = time.monotonic()


def check(name, value):
    REPORT['checks'][name] = bool(value)


def phase(name):
    REPORT['phases'].append({'phase': name, 'seconds': int(time.monotonic()-START)})
    io.write_json(OUT / (name + '.json'), REPORT)
    print('REVIEW_PHASE_COMPLETE ' + name, flush=True)


def count(db, sql):
    return int(db.execute(sql).fetchone()[0])


def aggregates(db, sql):
    """Call only with fixed queries projecting public dimensions and aggregates."""
    return list(io.sorted_rows(db, sql))


def main():
    global OUT
    require_goethe_nhr_slurm('stage09-independent-development-review')
    c.require_runtime()
    anchor = Path('/work/footprint/donyadidegan/safe_geocoding_pipeline').resolve()
    OUT = Path(os.environ['STAGE09_REVIEW_OUTPUT'])
    c.require(OUT.parent == anchor / 'derived/controlled/stage09/independent_review', 'REVIEW_OUTPUT_SCOPE_INVALID')
    OUT.mkdir(mode=0o700)
    root = anchor / 'derived/controlled/stage09/development/stage09_development_20260910T155542Z_3e10ac7c1309'
    public = anchor / 'derived/controlled/stage09/public_pack/stage09_public_pack_20260907_v1_3e10ac7c1309'
    stage08 = anchor / 'derived/controlled/stage08/development/stage08_development_20260902T132726Z_c04cb97214a9'
    raw_root = anchor / 'derived/controlled/stage09/public_raw/20260907_v1'
    executable = anchor / 'integration_stage09' / EXE
    lock_path = executable / 'docs/scientific_assets/stage09_reference_pack_lock_v1.json'
    for path in (root, public, stage08, raw_root, executable):
        upstream.reject_protected_scope_path(path)
    check('candidate_import_exact_checkout', Path(c.__file__).is_relative_to(executable))
    REPORT['review_job_id'] = os.environ['SLURM_JOB_ID']
    REPORT['review_sha'] = os.environ['STAGE09_REVIEW_SHA']
    with m.offline_network():
        manifest = io.validate_terminal(root, MANIFEST, True)
        pub = io.validate_terminal(public, PUBLIC, True)
        check('manifest_logical', manifest['logical_sha256'] == LOGICAL)
        check('candidate_not_accepted', manifest['stage09_accepted'] is False)
        check('executable_bindings', all(x['operational_provenance']['execution_git_sha'] == EXE for x in (manifest, pub)))
        paths = {}
        for base, doc in ((public, pub), (root, manifest)):
            for rec in doc['relations']:
                name = rec['name']
                paths[name] = [base / f['relative_path'] for f in rec['files']]
                for f in rec['files']:
                    check('physical_' + name + '_' + Path(f['relative_path']).name, c.sha256_file(base / f['relative_path']) == f['sha256'])
            from safe_geocoding_pipeline.preprocessing.stages import s09_reference_publication as publication
            for f in publication.inventory(doc):
                check('inventory_' + base.name + '_' + f['path'], (base/f['path']).stat().st_size == f['bytes'] and c.sha256_file(base/f['path']) == f['sha256'])
        lock = p.verify_lock(raw_root, lock_path)
        raw = p.PublicInputs(raw_root, lock, p.registry_rows(lock))
        accepted = upstream.consume_accepted_stage08(stage08)
        check('accepted_binding', manifest['stage08_binding'] == accepted.binding)
        check('accepted_binding_fingerprint', accepted.fingerprint.hex() == manifest['stage08_binding_sha256'])
        check('profile', m.scientific_profile(accepted.fingerprint, pub).hex() == manifest['profile_sha256'])
        check('contract', c.contract_fingerprint().hex() == manifest['contract_sha256'])
        check('schema_bundle', c.schema_bundle_fingerprint().hex() == manifest['schema_bundle_sha256'])
        check('dataset_header', m.dataset_fingerprint(bytes.fromhex(manifest['profile_sha256']), manifest['relations'], pub['logical_sha256'], upstream.STAGE08_RELATIONS['representation_occurrence_v1']).hex() == LOGICAL)
        phase('bindings')
        with io.bounded_connection(OUT/'spill', database=OUT/'review.duckdb') as db, io.bounded_connection(OUT/'meta-spill', memory='128MB', threads=1) as meta:
            accepted.register_views(db)
            for name, group in paths.items():
                db.execute('CREATE VIEW ' + name + ' AS SELECT * FROM ' + io.parquet_sql(group))
                key = ','.join(c.PRIMARY_KEYS[name])
                n = count(db, 'SELECT count(*) FROM ' + name)
                check('count_' + name, n == EXPECTED_COUNTS[name])
                check('pk_' + name, count(db, 'SELECT count(*) FROM (SELECT '+key+' FROM '+name+' GROUP BY ALL HAVING count(*)<>1)') == 0)
            db.execute('CREATE VIEW e AS SELECT * FROM candidate_reference_evidence')
            db.execute("CREATE VIEW context AS SELECT stage06_exact_candidate_id, CASE WHEN stage07_country_provenance_status='COUNTRY_UNANIMOUS_VALID' THEN upper(stage07_trusted_country_iso_code) ELSE 'UNRESOLVED' END country FROM candidate_evidence")
            db.execute('CREATE TABLE pairs AS SELECT stage06_exact_candidate_id,stable_source_row_id_v1, bool_or(stage08_representation=\'STANDARD\') is_standard, bool_or(stage08_representation=\'NATIVE\') is_native FROM stage08_occurrence GROUP BY ALL')
            db.execute('CREATE TABLE representations AS SELECT stage06_exact_candidate_id,bool_or(is_standard) is_standard,bool_or(is_native) is_native FROM pairs GROUP BY ALL')
            checks = {
                'capability_version_fk': 'SELECT count(*) FROM reference_capability a ANTI JOIN reference_registry b USING(reference_version_id)',
                'object_version_fk': 'SELECT count(*) FROM reference_object a ANTI JOIN reference_registry b USING(reference_version_id)',
                'object_parent_fk': 'SELECT count(*) FROM reference_object a LEFT JOIN reference_object b ON a.explicit_parent_id=b.reference_object_id WHERE a.explicit_parent_id IS NOT NULL AND b.reference_object_id IS NULL',
                'candidate_loss': 'SELECT count(*) FROM candidate_evidence a ANTI JOIN e USING(stage06_exact_candidate_id)',
                'candidate_fk': 'SELECT count(*) FROM e ANTI JOIN candidate_evidence USING(stage06_exact_candidate_id)',
                'source_pair_fk': "SELECT count(*) FROM e ANTI JOIN pairs USING(stage06_exact_candidate_id,stable_source_row_id_v1) WHERE evidence_scope='SOURCE_ROW'",
                'closed_states': "SELECT count(*) FROM e WHERE result_state NOT IN ('SUPPORTED','CONTRADICTED','NOT_FOUND','NOT_EVALUABLE')",
                'gn_contradictions': "SELECT count(*) FROM e WHERE reference_slot='GEONAMES_POSTAL' AND result_state='CONTRADICTED'",
                'gn_negative_authority': "SELECT count(*) FROM reference_capability a JOIN reference_registry b USING(reference_version_id) WHERE b.reference_id='GEONAMES_POSTAL' AND a.negative_authority",
                'association_not_contradiction': "SELECT count(*) FROM e WHERE reason_code='REFERENCE_ASSOCIATION_MISMATCH' AND result_state<>'NOT_FOUND'",
                'negative_authority': "SELECT count(*) FROM e a LEFT JOIN reference_capability b USING(capability_id) WHERE a.result_state='CONTRADICTED' AND (b.capability_id IS NULL OR NOT b.enabled OR NOT b.negative_authority)",
                'source_grain': "SELECT count(*) FROM (SELECT stage06_exact_candidate_id,stable_source_row_id_v1,question_catalog_id,reference_slot FROM e WHERE evidence_scope='SOURCE_ROW' GROUP BY ALL HAVING count(*)<>1)",
                'source_slot_totality': "SELECT count(*) FROM (SELECT p.stage06_exact_candidate_id,p.stable_source_row_id_v1,count(e.evidence_id) n FROM pairs p LEFT JOIN e ON p.stage06_exact_candidate_id=e.stage06_exact_candidate_id AND p.stable_source_row_id_v1=e.stable_source_row_id_v1 AND e.evidence_scope='SOURCE_ROW' GROUP BY ALL HAVING n<>18)",
                'parser_source_id_null': "SELECT count(*) FROM e WHERE evidence_scope='PARSER_CANDIDATE' AND stable_source_row_id_v1 IS NOT NULL",
                'q02_only_country_assessment': "SELECT count(*) FROM e WHERE country_assessment<>'COUNTRY_UNRESOLVED' AND (evidence_scope<>'SOURCE_ROW' OR question_catalog_id<>'Q02')",
                'capability_context': "SELECT count(*) FROM e JOIN context USING(stage06_exact_candidate_id) JOIN reference_capability USING(capability_id) WHERE country_scope<>CASE WHEN e.question_catalog_id IN ('Q01','Q14') THEN 'GLOBAL' ELSE country END",
            }
            for name, sql in checks.items():
                check(name, count(db, sql) == 0)
            REPORT['diagnostics']['states'] = aggregates(db,'SELECT result_state,count(*) n FROM e GROUP BY ALL ORDER BY ALL')
            REPORT['diagnostics']['family_states'] = aggregates(db,'SELECT reference_slot,result_state,count(*) n FROM e GROUP BY ALL ORDER BY ALL')
            REPORT['diagnostics']['candidate_evaluable'] = count(db,"SELECT count(DISTINCT stage06_exact_candidate_id) FROM e WHERE result_state<>'NOT_EVALUABLE'")
            REPORT['diagnostics']['gn_association_mismatches'] = count(db,"SELECT count(*) FROM e WHERE reason_code='REFERENCE_ASSOCIATION_MISMATCH'")
            REPORT['diagnostics']['q02'] = aggregates(db,"SELECT evidence_scope,result_state,reason_code,count(*) n FROM e WHERE question_catalog_id='Q02' GROUP BY ALL ORDER BY ALL")
            # Independent source full-code witness count; no candidate evidence result consulted.
            db.execute("CREATE VIEW iso_admin_codes AS SELECT country_code,list_extract(list_filter(fields,x -> x.field_name='code'),1).original_value code FROM reference_object WHERE object_kind='ISO_ADMIN'")
            REPORT['diagnostics']['source_full_iso_witnesses'] = count(db,"SELECT count(*) FROM pairs JOIN source_candidate_map USING(stable_source_row_id_v1) JOIN context USING(stage06_exact_candidate_id) JOIN iso_admin_codes ON upper(stage03_clean_region_in_country)=code WHERE country<>'UNRESOLVED'")
            # Expected parser scheduling counts derived from raw Stage 8 roles, independently of scheduler.
            db.execute("CREATE TABLE role_counts AS SELECT stage06_exact_candidate_id,stage08_safe_parser_evidence_component role_code,count(*) n FROM parser_component_evidence GROUP BY ALL")
            schedule_errors = 0
            atomic = {'Q04':('PARSER_POSTCODE',1),'Q05':('PARSER_POSTCODE',1),'Q09':('PARSER_CITY',2),'Q10':('PARSER_STATE',3),'Q12':('PARSER_ROAD',1),'Q14':('PARSER_COUNTRY',1)}
            for question in c.CATALOG:
                role, slots = atomic.get(question.question_id, ('NONE',len(question.references)))
                sql = "WITH observed AS (SELECT stage06_exact_candidate_id,count(*) n FROM e WHERE evidence_scope='PARSER_CANDIDATE' AND question_catalog_id=? GROUP BY ALL) SELECT count(*) FROM candidate_evidence a LEFT JOIN role_counts r ON a.stage06_exact_candidate_id=r.stage06_exact_candidate_id AND r.role_code=? LEFT JOIN observed o ON a.stage06_exact_candidate_id=o.stage06_exact_candidate_id WHERE coalesce(o.n,0)<>greatest(coalesce(r.n,0),1)*?"
                schedule_errors += db.execute(sql,[question.question_id,role,slots]).fetchone()[0]
            check('independent_parser_scheduling', schedule_errors == 0)
            phase('relational_sql')
            # Resolve Q04 ONLY inside controlled compute, never emit values or row identities.
            db.execute("""CREATE TABLE pattern_inputs AS
              SELECT e.evidence_id,e.stage06_exact_candidate_id,e.stable_source_row_id_v1,e.evidence_scope,e.result_state,e.reason_code,e.rule_capability_id,e.arguments[2] argument,c.country,
              CASE WHEN e.evidence_scope='SOURCE_ROW' THEN s.stage03_clean_postcode ELSE p.stage08_raw_libpostal_value END input_value,
              CASE WHEN e.evidence_scope='SOURCE_ROW' THEN pairs.is_standard ELSE r.is_standard END is_standard,
              CASE WHEN e.evidence_scope='SOURCE_ROW' THEN pairs.is_native ELSE r.is_native END is_native
              FROM e JOIN context c USING(stage06_exact_candidate_id)
              LEFT JOIN source_candidate_map s USING(stable_source_row_id_v1)
              LEFT JOIN parser_component_evidence p ON e.stage06_exact_candidate_id=p.stage06_exact_candidate_id AND e.arguments[2].component_ordinal=p.stage08_component_ordinal
              LEFT JOIN pairs ON e.stage06_exact_candidate_id=pairs.stage06_exact_candidate_id AND e.stable_source_row_id_v1=pairs.stable_source_row_id_v1
              JOIN representations r ON e.stage06_exact_candidate_id=r.stage06_exact_candidate_id
              WHERE e.question_catalog_id='Q04'""")
            data = raw.json_data(c.LIA)
            selectors = next(x['country_scope_selector'] for x in lock['capability_registry']['rules'] if x['reference_id']==c.LIA and x['question_catalog_id']=='Q04')
            rule_counts, shapes, alternate_matches = Counter(), Counter(), Counter()
            oracle_mismatch = digest_mismatch = engine_mismatch = pointer_mismatch = 0
            ascii_map = str.maketrans('abcdefghijklmnopqrstuvwxyz','ABCDEFGHIJKLMNOPQRSTUVWXYZ')
            for row in io.sorted_rows(db,'SELECT * FROM pattern_inputs',batch_rows=256):
                country, value, arg = row['country'], row['input_value'], row['argument']
                normalized = value.translate(ascii_map) if value is not None else None
                rule = data.get(country,{}).get('zip')
                available = country != 'UNRESOLVED' and bool(value) and country in selectors and bool(rule)
                expected = ('SUPPORTED' if re.fullmatch(rule, normalized, re.ASCII) else 'CONTRADICTED') if available else 'NOT_EVALUABLE'
                oracle_mismatch += expected != row['result_state']
                if normalized is not None:
                    digest_mismatch += arg['normalization_id'] != c.FORM_NORM or arg['normalized_value_sha256'] != c.identity('NORMALIZED_VALUE',(c.FORM_NORM,normalized))
                if value is not None:
                    pointer_mismatch += arg['origin_field'] != ('stage03_clean_postcode' if row['evidence_scope']=='SOURCE_ROW' else 'stage08_raw_libpostal_value')
                representation = 'BOTH' if row['is_standard'] and row['is_native'] else 'STANDARD_ONLY' if row['is_standard'] else 'NATIVE_ONLY'
                key = (country,row['evidence_scope'],representation,arg['normalization_id'],country+'/zip',row['result_state'])
                rule_counts[key] += 1
                if available:
                    observed = meta.execute('SELECT regexp_full_match(?,?)',[normalized,rule]).fetchone()[0]
                    engine_mismatch += observed != (expected == 'SUPPORTED')
                    if expected == 'CONTRADICTED':
                        shape = 'ASCII_DIGITS_'+str(len(normalized)) if re.fullmatch('[0-9]+', normalized) and len(normalized)<=12 else 'ASCII_DIGITS_LONG' if re.fullmatch('[0-9]+', normalized) else 'NON_ASCII_DIGITS' if normalized.isdecimal() else 'OTHER_TEXT_OR_SEPARATORS'
                        shapes[(country,row['evidence_scope'],shape)] += 1
                        probes = {'trim_whitespace':normalized.strip(),'remove_ascii_spaces_hyphens':normalized.replace(' ','').replace('-',''),'prepend_one_zero':'0'+normalized}
                        for method, probe in probes.items():
                            if probe != normalized and re.fullmatch(rule,probe,re.ASCII):
                                alternate_matches[(country,row['evidence_scope'],method)] += 1
                        if normalized.startswith('0'):
                            alternate_matches[(country,row['evidence_scope'],'already_has_leading_zero')] += 1
            check('q04_independent_state_oracle',oracle_mismatch == 0)
            check('q04_independent_normalized_digests',digest_mismatch == 0)
            check('q04_independent_pointer_fields',pointer_mismatch == 0)
            check('q04_python_ascii_re2_agreement',engine_mismatch == 0)
            REPORT['diagnostics']['q04_rule_representation'] = [dict(zip(('country','scope','representation','normalization','rule','state','n'),(*k,n))) for k,n in sorted(rule_counts.items())]
            REPORT['diagnostics']['q04_conflict_shapes'] = [dict(zip(('country','scope','shape','n'),(*k,n))) for k,n in sorted(shapes.items())]
            REPORT['diagnostics']['q04_counterfactual_diagnostics'] = [dict(zip(('country','scope','diagnostic','n'),(*k,n))) for k,n in sorted(alternate_matches.items())]
            REPORT['diagnostics']['q04_candidate_concentration'] = aggregates(db,"SELECT country,evidence_scope,count(*) evaluable_checks,count(DISTINCT stage06_exact_candidate_id) candidates,count(*) FILTER(WHERE result_state='CONTRADICTED') conflicts,count(DISTINCT stage06_exact_candidate_id) FILTER(WHERE result_state='CONTRADICTED') conflict_candidates,count(DISTINCT (stage06_exact_candidate_id,argument.normalized_value_sha256)) unique_candidate_values FROM pattern_inputs WHERE result_state<>'NOT_EVALUABLE' GROUP BY ALL ORDER BY ALL")
            REPORT['diagnostics']['q04_largest_candidate_bins'] = aggregates(db,"WITH x AS (SELECT country,evidence_scope,stage06_exact_candidate_id,count(*) n,count(*) FILTER(WHERE result_state='CONTRADICTED') conflicts FROM pattern_inputs WHERE result_state<>'NOT_EVALUABLE' GROUP BY ALL) SELECT country,evidence_scope,count(*) candidates,max(n) max_checks_per_candidate,max(conflicts) max_conflicts_per_candidate,sum(n) evaluable,sum(conflicts) conflicts FROM x GROUP BY ALL ORDER BY ALL")
            REPORT['diagnostics']['q08'] = aggregates(db,"SELECT country,evidence_scope,result_state,reason_code,r.scope_locator rule_locator,count(*) n FROM e JOIN context USING(stage06_exact_candidate_id) LEFT JOIN reference_capability r ON e.rule_capability_id=r.capability_id WHERE e.question_catalog_id='Q08' GROUP BY ALL ORDER BY ALL")
            phase('postcode_oracle')
            # Full original validators, independently executed against immutable bytes.
            view = m._small_view(public,pub,raw,meta)
            index_paths = [public/f['relative_path'] for f in pub['reference_index']['files']]
            REPORT['diagnostics']['candidate_integrity_validator'] = v.validate_integrity(db,view,paths['candidate_reference_evidence'],paths['reference_match_member'],paths['reference_object'],index_paths,profile=bytes.fromhex(manifest['profile_sha256']),stage08_logical=bytes.fromhex(upstream.STAGE08_LOGICAL_SHA256),counts=upstream.COUNTS)
            phase('complete_integrity')
            # Recompute complete coverage, including distinct occurrence incidence.
            cov.register_question_slots(db)
            expected_coverage = sorted(cov.coverage_rows(db,view.registry[c.ISO]['countries'],upstream.COUNTS), key=lambda row: tuple(row[k] for k in c.PRIMARY_KEYS['coverage_summary']))
            check('coverage_recomputed',all(a==b for a,b in zip_longest(expected_coverage,io.parquet_rows(paths['coverage_summary']))))
            for base, doc in ((public,pub),(root,manifest)):
                for rec in doc['relations']:
                    io.validate_relation(base,rec)
                    check('logical_'+rec['name'],True)
                    phase('logical_'+rec['name'])
            # Complete public raw-object and index rederivation through audited helpers.
            idx.validate_public_pack(public,PUBLIC,inputs=raw,execution_sha=EXE)
            check('complete_public_pack_reopen',True)
            phase('public_reopen')
        # Recheck immutable terminal manifests/topology after all read-only scans.
        io.validate_terminal(root,MANIFEST,True)
        io.validate_terminal(public,PUBLIC,True)
        check('final_terminal_reopen',True)
        REPORT['failed_checks'] = sorted(k for k,value in REPORT['checks'].items() if not value)
        phase('complete')


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        # No traceback/str(error): SQL, values and row IDs must never reach logs.
        if 'OUT' in globals() and OUT.exists():
            REPORT['harness_exception_type'] = type(error).__name__
            REPORT['harness_traceback_locations'] = []
            tb = error.__traceback__
            while tb is not None:
                REPORT['harness_traceback_locations'].append({'file':Path(tb.tb_frame.f_code.co_filename).name,'line':tb.tb_lineno})
                tb = tb.tb_next
            io.write_json(OUT/'harness_failure.json',REPORT)
        print('REVIEW_HARNESS_INCOMPLETE '+type(error).__name__,flush=True)
        sys.exit(1)
