from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from apps.graphrag.evaluation import DEFAULT_CASES_PATH, evaluate_golden_cases, load_golden_cases


class Command(BaseCommand):
    help = "Run GraphRAG golden-case evaluation and evidence consistency checks."

    def add_arguments(self, parser):
        parser.add_argument(
            "--cases",
            default=str(DEFAULT_CASES_PATH),
            help="Path to a golden cases JSON file.",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Print the full evaluation report as JSON.",
        )
        parser.add_argument(
            "--allow-empty",
            action="store_true",
            help="Exit successfully when all cases are disabled or the file has no cases.",
        )

    def handle(self, *args, **options):
        try:
            cases = load_golden_cases(options["cases"])
        except Exception as exc:
            raise CommandError(f"Unable to load golden cases: {exc}") from exc

        report = evaluate_golden_cases(cases)
        summary = report["summary"]

        if options["json"]:
            self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            self.stdout.write(
                "GraphRAG evaluation: "
                f"{summary['passed']} passed, {summary['failed']} failed, "
                f"{summary['skipped']} skipped, {summary['enabled']} enabled"
            )
            for result in report["results"]:
                status = result["status"].upper()
                self.stdout.write(f"[{status}] {result['id']}")
                for failure in result.get("failures", []):
                    self.stdout.write(f"  - {failure}")

        if summary["enabled"] == 0 and not options["allow_empty"]:
            raise CommandError("No enabled golden cases. Enable cases or pass --allow-empty.")
        if summary["failed"]:
            raise CommandError(f"{summary['failed']} GraphRAG golden case(s) failed.")
