"""Explicit B2 phase entrypoint. No installed live adapter or permission defaults.

A separately reviewed runtime port supplies authority, local evidence, exact
accepted-input readers and transport. This module owns phase sequencing; the
port cannot replace calibration, capture, recovery or publication algorithms.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import importlib.util
from pathlib import Path
from typing import Any

from .stages import s12_b2_contract as b
from .stages import s12_b2_calibration as calibration
from .stages import s12_b2_planning as planning
from .stages import s12_b2_pipeline as pipeline
from .stages import s12_b2_publication as publication
from .stages import s12_b2_evidence as evidence
from .stages import s12_b2_phase_io as phase_io
from .stages import s12_b2_catalog as catalogs
from .stages import s12_b2_lineage as lineage
from .stages import s12_b2_local_preparation as local
from contextlib import ExitStack
from .stages import s12_public_journal as journal
from .stages import s12_storage as io
from .stages import s12_retrieval_contract as c

PHASES = (
    "build-catalog",
    "build-workload",
    "offline-preflight",
    "preflight",
    "plan-calibration",
    "prepare-bootstrap",
    "run-campaign",
    "close-campaign",
    "evaluate-calibration",
    "run-direct-n",
    "close-window",
    "publish",
    "reopen",
)


@dataclass
class Session:
    """Runtime injection only; never serialized as authority or scientific data."""

    port: Any
    configuration: dict
    output: Path
    scratch: Path
    authorization_sha256: str

    def require(self, phase):
        if hasattr(self.port, "bind_session"):
            self.port.bind_session(
                phase,
                self.configuration,
                self.output,
                self.scratch,
                self.authorization_sha256,
            )
        b.require(phase in PHASES, "B2_PHASE_INVALID")
        b.validate_type(self.authorization_sha256, "D")
        b.require(
            self.port.population_scope in (b.DEVELOPMENT, b.SYNTHETIC),
            "B2_POPULATION_SCOPE",
        )
        b.require(
            bool(self.port.test_only) == (self.port.population_scope == b.SYNTHETIC),
            "B2_POPULATION_SCOPE",
        )
        if self.port.population_scope == b.DEVELOPMENT:
            from ..execution_policy import require_goethe_nhr_slurm

            require_goethe_nhr_slurm("stage12 observational " + phase)
        self.port.authority.require(
            "phase_" + phase,
            self.authorization_sha256,
            {
                "configuration_sha256": b.digest(self.configuration),
                "population_scope": self.port.population_scope,
            },
        )
        io.private_directory(self.output.parent)
        io.private_directory(self.scratch.parent)


def execute(phase: str, session: Session):
    # Port cleanup cannot replace an initiating failure. Successful return still
    # requires cleanup/source validation to succeed; no result is printed early.
    try:
        with ExitStack() as resources:
            result = _execute(phase, session, resources)
    except BaseException:
        try:
            if hasattr(session.port, "close"):
                session.port.close()
        except BaseException:
            pass
        raise
    if hasattr(session.port, "close"):
        session.port.close()
    return result


def catalog_for(session, resources):
    port, config = session.port, session.configuration
    if port.test_only:
        return port.open_catalog()  # Explicit invented-fixture adapter only.
    port.gate.check()
    binding = port.records.get(config["input_binding_sha256"], "stage11_input_binding")
    port.authority.require("protected_input", b.digest(binding), binding)
    catalog = catalogs.Catalog(
        Path(config["catalog_path"]),
        binding,
        expected_file_sha256=config["catalog_file_sha256"],
    )
    resources.callback(catalog.close)
    catalog.verify()
    return catalog


def open_observations(session, catalog, resources):
    port = session.port
    result = []
    specs = session.configuration["calibration_publications"]
    b.require(type(specs) is list and 1 <= len(specs) <= 10, "B2_CALIBRATION_TOTALITY")
    for i, spec in enumerate(specs):
        b.require(set(spec) == {"path", "manifest_sha256"}, "B2_ARTIFACT_SPEC")
        root = Path(spec["path"])
        expected = bytes.fromhex(spec["manifest_sha256"])
        b.require(
            b.sha(io.read(root / "manifest.json")) == expected, "B2_MANIFEST_HASH"
        )
        retained = io.metadata(io.read(root / "campaign.json"))
        # Immutable publication inventory is checked before its operational path is used.
        manifest = io.metadata(io.read(root / "manifest.json"))
        io.verify_inventory(
            root,
            manifest["inventory"],
            extra={"manifest.json", "registration.json", "_COMMITTED"},
        )
        campaign = phase_io.CampaignReader(
            Path(retained["operational_root"]),
            catalog=catalog,
            rules=port.response_rules,
            gate=port.gate,
            closure_hash=retained["campaign_closure_sha256"],
            scratch=session.scratch / ("campaign_" + str(i)),
            control_adapters=port.control_adapters,
        )
        resources.callback(campaign.close)
        counter = [0]

        def validate(
            root=root, expected=expected, campaign=campaign, counter=counter, i=i
        ):
            counter[0] += 1
            return publication.validate_terminal(
                root,
                expected,
                committed=True,
                validate_science=lambda r, m: publication.scientific_reopen(
                    r,
                    m,
                    catalog=catalog,
                    rules=port.response_rules,
                    scratch=session.scratch / (f"artifact_{i}_{counter[0]}"),
                    memory_bytes=session.configuration["external_sort_memory_bytes"],
                    gate=port.gate,
                    verify_campaign=campaign.validate,
                ),
            )

        reader = publication.ArtifactReader(
            root,
            expected,
            scratch=session.scratch / (f"artifact_{i}.sqlite"),
            catalog=catalog,
            rules=port.response_rules,
            validate_artifact=validate,
        )
        resources.callback(reader.close)
        result.append(reader.observation)
    return tuple(result)


def calibration_checks(session, catalog, resources, plan):
    port, config = session.port, session.configuration
    reader_root = session.scratch.parent / (session.scratch.name + "_readers")
    io.reserve(reader_root)
    reader_session = Session(
        port, config, session.output, reader_root, session.authorization_sha256
    )
    observations = (
        open_observations(reader_session, catalog, resources)
        if config["N_decision_sha256"] is not None
        else ()
    )
    n = (
        port.records.get(config["N_decision_sha256"], "n_decision")
        if config["N_decision_sha256"] is not None
        else None
    )
    b.require(n is None or bool(observations), "B2_CALIBRATION_TOTALITY")

    def adequacy():
        selection, _ = planning.load_selection(
            port.records,
            port.gate.selection_hash,
            catalog,
            authority=port.authority,
            scratch=reader_root
            / ("selection_" + str(len(list(reader_root.iterdir()))) + ".sqlite"),
        )
        return calibration.evaluate(
            catalog,
            selection,
            observations,
            window_hash=plan["window_plan_sha256"],
            selection_hash=port.gate.selection_hash,
            authority=port.authority,
            comparison_writer=lambda row: None,
        )

    def retention():
        full = next(x for x in observations if x.kind == "FULL_C")
        if n["result_limit"] == full.size:
            candidate = full
        else:
            reader = phase_io.CampaignReader(
                port.segment,
                catalog=catalog,
                rules=port.response_rules,
                gate=port.gate,
                closure_hash=config["campaign_closure_sha256"],
                scratch=reader_root
                / ("direct_reader_" + str(len(list(reader_root.iterdir())))),
                control_adapters=port.control_adapters,
            )
            resources.callback(reader.close)
            candidate = reader.observation
        if n["result_limit"] == full.size:
            b.require(
                candidate.publication_sha256 == full.publication_sha256
                and plan["workload_kind"] == "FULL_C",
                "B2_FULL_C_REUSE",
            )
            full.validate()
        else:
            calibration.direct_n(
                catalog,
                full,
                candidate,
                N=n["result_limit"],
                decision=n,
                authority=port.authority,
                comparison_writer=lambda row: None,
            )

    return n, adequacy if n else None, retention if n else None


def _execute(phase: str, session: Session, resources):
    """Return metadata only; source fields and exception bodies never go to CLI."""
    session.require(phase)
    port = session.port
    config = session.configuration
    if getattr(port, "local_only", False) and phase in {
        "prepare-bootstrap",
        "build-workload",
        "offline-preflight",
    }:
        return local.execute_metadata(phase, session, resources, catalog_for)
    if phase == "build-catalog":
        b.require(
            port.population_scope == b.DEVELOPMENT, "B2_ACCEPTED_POPULATION_REQUIRED"
        )
        port.gate.check()
        binding = port.records.get(
            config["input_binding_sha256"], "stage11_input_binding"
        )
        io.reserve(session.scratch)
        projection = lineage.LineageProjection.open(
            stage08_root=Path(config["stage08_root"]),
            stage09_root=Path(config["stage09_root"]),
            stage06_root=Path(config["stage06_root"]),
            scratch=session.scratch / "lineage",
            memory_bytes=config["external_sort_memory_bytes"],
            authority=port.authority,
            interpretation=config["witness_interpretation"],
            interpretation_sha256=config["witness_interpretation_sha256"],
        )
        resources.callback(projection.close)
        if getattr(port, "local_only", False):
            resources.enter_context(local.lineage_scope(port, projection))
        catalog = catalogs.build_accepted(
            session.output,
            Path(config["stage11_root"]),
            binding,
            repository=Path(__file__).resolve().parents[3],
            lineage=projection,
            authority=port.authority,
            scratch=session.scratch / "catalog_join",
            memory_bytes=config["external_sort_memory_bytes"],
        )
        resources.callback(catalog.close)
        result = {
            "catalog_file_sha256": catalog.file_sha256,
            "input_binding_sha256": b.digest(binding),
            "lineage_binding_sha256": projection.binding_sha256,
        }
        io.write(
            session.output.parent / (session.output.name + ".identity.json"),
            b.canonical(result),
        )
    elif phase == "plan-calibration":
        catalog = catalog_for(session, resources)
        selected = calibration.select(
            catalog,
            session.scratch,
            C=config["C"],
            T=config["T"],
            supported=port.authority.supported_size(
                config["capability_evidence_sha256"]
            ),
            authority=port.authority,
            decision_hash=config["depth_decision_sha256"],
        )
        core = planning.seal_core(
            port.records,
            selected,
            catalog,
            lineage_hash=config["lineage_binding_sha256"],
            capability_hash=config["capability_evidence_sha256"],
            decision_hash=config["depth_decision_sha256"],
            owner=port.assert_administrative_owner,
            secret_guard=port.secret_guard,
        )
        result = {"calibration_plan_sha256": core, "scientific_N_selected": False}
    elif phase == "prepare-bootstrap":
        # A bootstrap cannot name a future admission hash. Acquire the finite
        # reviewed preflight records first, then bind the returned actual hash
        # in a separately scoped admission/preflight configuration.
        result = {
            "bootstrap_acquisition_sha256": port.prepare_bootstrap(),
            "admission_issued": False,
            "dispatch_authorized": False,
        }
    elif phase == "preflight":
        # Bootstrap is the sole writer before the campaign's sole writer exists.
        values = port.campaign_inputs()
        profile, plan, start, science, admission, works = values
        catalog = catalog_for(session, resources)
        catalog.verify()
        port.gate.validate_campaign(start, plan, admission)
        port.gate.validate_workload(
            catalog, profile, plan, works, admission, session.scratch
        )
        result = {
            "ready_for_separate_workload_decision": True,
            "profile_sha256": b.digest(profile),
            "plan_sha256": b.digest(plan),
            "admission_sha256": b.digest(admission),
            "implementation_does_not_authorize_dispatch": True,
        }
    elif phase in ("run-campaign", "run-direct-n"):
        profile, plan, start, science, admission, works = port.campaign_inputs()
        b.require(
            (phase == "run-direct-n") == (plan["workload_kind"] == "DIRECT_N"),
            "B2_PHASE_INVALID",
        )
        catalog = catalog_for(session, resources)
        port.gate.validate_campaign(start, plan, admission)
        port.gate.validate_workload(
            catalog, profile, plan, works, admission, session.scratch
        )
        port.gate.admit(
            admission["preflight_observation_sha256"], admission["segment_nonce"]
        )
        result = pipeline.run_segment(
            session.output,
            profile,
            plan,
            start,
            science,
            admission,
            catalog=catalog,
            work_factory=works,
            gate=port.gate,
            clock=port.clock,
            dispatch=port.dispatch,
            runtime_inventory=port.runtime_inventory,
            key=port.runtime_key(),
            rules=port.response_rules,
            control_adapters=port.control_adapters,
            free_bytes=port.free_bytes,
            writer_release_evidence=config["writer_release_authority_sha256"],
            close_segment=port.postflight_records,
            predecessor=port.predecessor,
            pause_requested=port.pause_requested,
            notice=port.notice,
            phase_check=port.check_deadline,
            phase_remaining_seconds=lambda: (
                max(0, port.deadline - port.clock.now_ns()) / 1e9
            ),
        )
    elif phase == "close-campaign":
        profile, plan, start, science, admission, works = port.campaign_inputs()
        port.verify_campaign()
        node = port.segment
        segments = []
        while node is not None:
            segments.append(
                b.parse(
                    io.read(node / "snapshot.json"), b.REGISTRY["names"]["SNAPSHOT"]
                )["segment_closure_sha256"]
            )
            node = journal.predecessor_root(node)
        result = evidence.campaign_closure(
            port.records,
            config["campaign_closure_sha256"],
            plan=plan,
            start=science,
            segments=list(reversed(segments)),
            authority=port.gate,
            population_scope=port.population_scope,
        )
    elif phase == "evaluate-calibration":
        catalog = catalog_for(session, resources)
        selection, _ = planning.load_selection(
            port.records,
            config["selection_sha256"],
            catalog,
            authority=port.authority,
            scratch=session.scratch,
        )
        # Scratch selection is a file; artifact readers use its private sibling directory.
        readers_root = session.scratch.parent / (session.scratch.name + "_readers")
        io.reserve(readers_root)
        reader_session = Session(
            port, config, session.output, readers_root, session.authorization_sha256
        )
        observations = open_observations(reader_session, catalog, resources)
        phase_writer = phase_io.PhaseOutput(
            session.output,
            writer_guard_ms=config["phase_writer_guard_ms"],
            max_bytes=config["phase_output_max_bytes"],
            max_rows=config["phase_output_max_rows"],
            secret_guard=port.secret_guard,
        )
        resources.callback(phase_writer.abort)
        result = calibration.evaluate(
            catalog,
            selection,
            observations,
            window_hash=config["window_plan_sha256"],
            selection_hash=config["selection_sha256"],
            authority=port.authority,
            comparison_writer=phase_writer.append,
        )
        result = phase_writer.finish(
            result,
            inputs={
                "selection_sha256": config["selection_sha256"],
                "window_plan_sha256": config["window_plan_sha256"],
                "publications": config["calibration_publications"],
                "configuration_sha256": b.digest(config),
                "authority_sha256": session.authorization_sha256,
            },
        )
    elif phase == "close-window":
        result = evidence.window_closure(
            port.records,
            config["window_closure_sha256"],
            window_hash=config["window_plan_sha256"],
            campaigns=config["ordered_campaign_closure_hashes"],
            authority=port.gate,
        )
        # The separately reviewed append-only authority registry must record this
        # closing event before any further session can authorize dispatch.
        port.register_closed_window(config["window_closure_sha256"])
    elif phase == "publish":
        profile, plan, start, science, admission, works = port.campaign_inputs()
        catalog = catalog_for(session, resources)
        n, adequacy, retention = calibration_checks(session, catalog, resources, plan)
        result = publication.publish_campaign(
            session.output,
            session.scratch,
            segment=port.segment,
            start=start,
            scientific_start=science,
            profile=profile,
            plan=plan,
            catalog=catalog,
            rules=port.response_rules,
            gate=port.gate,
            campaign_closure_hash=config["campaign_closure_sha256"],
            verify_campaign=port.verify_campaign,
            memory_bytes=config["external_sort_memory_bytes"],
            window_closure_hash=config["window_closure_sha256"],
            calibration_inventory=config["calibration_inventory"],
            n_decision=n,
            verify_calibration=adequacy if n else None,
            verify_final_retention=retention if n else None,
        )
    elif phase == "reopen":
        catalog = catalog_for(session, resources)
        port.verify_campaign()
        retained = io.metadata(
            io.read(Path(config["publication_path"]) / "campaign.json")
        )
        n, adequacy, retention = calibration_checks(
            session, catalog, resources, retained["plan"]
        )
        result = publication.validate_terminal(
            Path(config["publication_path"]),
            bytes.fromhex(config["manifest_sha256"]),
            committed=True,
            validate_science=lambda root, manifest: publication.scientific_reopen(
                root,
                manifest,
                catalog=catalog,
                rules=port.response_rules,
                scratch=session.scratch,
                memory_bytes=config["external_sort_memory_bytes"],
                gate=port.gate,
                verify_campaign=port.verify_campaign,
                verify_calibration=adequacy,
                verify_final_retention=retention,
            ),
        )
    else:
        raise c.Stage12Error("B2_PHASE_INVALID")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=PHASES)
    parser.add_argument("--configuration", type=Path, required=True)
    parser.add_argument("--configuration-sha256", required=True)
    parser.add_argument("--runtime-port", type=Path, required=True)
    parser.add_argument("--runtime-port-sha256", required=True)
    parser.add_argument("--authorization-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scratch", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        # These are explicit reviewed code/metadata inputs. No discovery through
        # environment variables, shell, service clients or credential stores.
        raw = io.read(args.configuration, limit=b.MAX_METADATA)
        code = io.read(args.runtime_port, limit=b.MAX_METADATA)
        b.require(
            b.sha(raw).hex() == args.configuration_sha256
            and b.sha(code).hex() == args.runtime_port_sha256,
            "B2_RUNTIME_INPUT_CHANGED",
        )
        config = io.metadata(raw)
        b.require(
            config["runtime_port_sha256"] == args.runtime_port_sha256,
            "B2_RUNTIME_INPUT_CHANGED",
        )
        spec = importlib.util.spec_from_file_location(
            "_stage12_explicit_reviewed_port", args.runtime_port
        )
        b.require(spec is not None and spec.loader is not None, "B2_PORT_REQUIRED")
        module = importlib.util.module_from_spec(spec)
        # Execute the exact verified bytes, avoiding a path reread/import race.
        exec(compile(code, str(args.runtime_port), "exec"), module.__dict__)
        port = module.create_port(config)
        result = execute(
            args.phase,
            Session(port, config, args.output, args.scratch, args.authorization_sha256),
        )
        print(
            b.canonical(
                {
                    "phase": args.phase,
                    "result_sha256": b.digest(result),
                    "status": "OFFLINE_OR_EXPLICITLY_AUTHORIZED_PHASE_COMPLETE",
                    "stage12_accepted": False,
                }
            ).decode(),
            end="",
        )
        return 0
    except Exception:
        # Exceptions may contain protected query/config material; never echo them.
        print("STAGE12_B2_PHASE_FAILED; controlled evidence must be reviewed")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
