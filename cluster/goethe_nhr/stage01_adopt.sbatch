#!/usr/bin/env bash
#SBATCH --job-name=safe-stage01-adopt
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=02:00:00
#SBATCH --output=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.out
#SBATCH --error=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.err

set -euo pipefail
umask 077

readonly DATA_ROOT="/work/footprint/donyadidegan/safe_geocoding_pipeline"
: "${SLURM_JOB_ID:?SLURM_JOB_ID is required}"
: "${STAGE01_GIT_COMMIT:?submit with the exact reviewed Stage 1 commit}"
: "${STAGE01_INTEGRATION_ROOT:?submit with an exact detached integration worktree}"
readonly INTEGRATION_ROOT="$(realpath -e -- "${STAGE01_INTEGRATION_ROOT}")"

readonly STAGE00_RECORD="${DATA_ROOT}/reports/generated/stage00/stage00_phase01_20260810T151626Z_7df9bc8f_accepted_v1/stage00_adoption.json"
readonly PHASE01_RUN="${DATA_ROOT}/reports/generated/phase01/phase01_20260810T151626Z_7df9bc8f"
readonly PHASE02_RUN="${DATA_ROOT}/staging/controlled/phase02_v1/runs/phase02_20260810T173851Z_1349152b"
readonly PHASE02_REPORTS="${DATA_ROOT}/reports/generated/phase02/phase02_20260810T173851Z_1349152b"
readonly OUTPUT="${DATA_ROOT}/reports/generated/stage01/stage01_phase02_20260810T173851Z_1349152b_implemented_pending_review_v1"

cd "${INTEGRATION_ROOT}"
source "${DATA_ROOT}/.venv-goethe-nhr/bin/activate"
export PYTHONPATH="${INTEGRATION_ROOT}/src"
export SAFE_EXECUTION_SITE=goethe-nhr
export PYTHONDONTWRITEBYTECODE=1

readonly ACTUAL_COMMIT="$(git rev-parse HEAD)"
[[ "${ACTUAL_COMMIT}" == "${STAGE01_GIT_COMMIT}" ]] || {
  echo "STAGE01_COMMIT_MISMATCH" >&2
  exit 1
}
[[ -z "$(git status --porcelain)" ]] || {
  echo "STAGE01_WORKTREE_DIRTY" >&2
  exit 1
}

echo "job_id=${SLURM_JOB_ID}"
echo "git_commit=${ACTUAL_COMMIT}"
echo "stage=stage01_production_bundle_adoption"

python - "${STAGE00_RECORD}" "${PHASE01_RUN}" "${PHASE02_RUN}" \
  "${PHASE02_REPORTS}" "${OUTPUT}" "${STAGE01_GIT_COMMIT}" "${SLURM_JOB_ID}" <<'PY'
from pathlib import Path
import sys

from safe_geocoding_pipeline.preprocessing.stages.s01_ingestion import adopt_phase02_bundle

outcome = adopt_phase02_bundle(
    Path(sys.argv[3]),
    Path(sys.argv[4]),
    Path(sys.argv[2]),
    Path(sys.argv[1]),
    Path(sys.argv[5]),
    expected_stage00_adoption_sha256="5d96acf5b1726287c112bf188a2da47da53a61b57cc119566a4ad33948d01778",
    expected_source_population_sha256="bdedb3f425a337048aaf21245b76246f92a36693cdbf0e28acb16f18b14fffc3",
    expected_scientific_inventory_sha256="551d893a8c6d16b799c1e38ecf4715cbe3bb0865d811eb44aaa6f46fa45b2631",
    expected_parser_contract_fingerprint="d071da05a76ca7c6ae5111894628fe8a5427f354838dbe0eb84e6cdf6ecd4b79",
    expected_phase02_run_id="phase02_20260810T173851Z_1349152b",
    expected_phase02_producing_git_commit="1349152bcbfa240aa402c9794f4c4351c94100ec",
    adopting_git_commit=sys.argv[6],
    adopting_git_dirty=False,
    production=True,
    operational_metadata={"slurm_job_id": sys.argv[7], "execution_site": "goethe-nhr"},
)
print(f"status=IMPLEMENTED_PENDING_FINAL_REVIEW")
print(f"source_files={outcome.bundle.source_file_count}")
print(f"total_rows={outcome.bundle.total_row_count}")
print(f"physical_shards={len(outcome.bundle.shards)}")
print(f"total_parquet_bytes={outcome.bundle.total_parquet_bytes}")
print(f"logical_dataset_sha256={outcome.bundle.logical_dataset_sha256_v1}")
print(f"adoption_record_sha256={outcome.adoption_record_sha256}")
print("source_csv_access=NOT_PERFORMED")
print("parquet_rewrite=NOT_PERFORMED")
PY

echo "STAGE01_ADOPTION_VALIDATION_PASS"
