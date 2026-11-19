import json
import os
from pathlib import Path
import subprocess
import tempfile

root = Path.cwd()
package = root / "packages/landmines"
runner = package / "node_modules/.bin/vitest"
assert runner.is_file(), runner
with tempfile.TemporaryDirectory(prefix=".environment-probe-", dir=package) as folder:
    probe = Path(folder)
    (probe / "vitest.config.mjs").write_text(
        'export default { test: { environment: "node", include: ["*.test.mjs"] } };\n'
    )
    (probe / "environment.mjs").write_text(
        'export default { name: "directive-probe", viteEnvironment: "ssr",\n'
        'setup(global, options) { global.environmentProbe = options;\n'
        'return { teardown() { delete global.environmentProbe; } }; } };\n'
    )
    bodies = {}
    forms = [
        ("vitest-line", "// @vitest-environment ./environment.mjs\n// @vitest-environment-options {\"value\": 21}\n", 21),
        ("vitest-block", "/**\n * @vitest-environment ./environment.mjs\n * @vitest-environment-options {\"value\": 22}\n */\n", 22),
        ("jest-block", "/**\n * @jest-environment ./environment.mjs\n * @jest-environment-options {\"value\": 23}\n */\n", 23),
    ]
    for name, directive, value in forms:
        file = probe / f"{name}.test.mjs"
        body = (
            'import { expect, test } from "vitest";\n'
            f'test("environment receives its per-file options", () => {{\n'
            f'  expect(JSON.stringify(globalThis.environmentProbe)).toContain(\'"value":{value}\');\n'
            '});\n'
        )
        file.write_text(directive + body)
        bodies[file] = body

    def run(name, failures):
        report = Path(os.environ["RUNNER_TEMP"]) / f"{name}.json"
        result = subprocess.run(
            [str(runner), "run", "--root", str(probe), "--config", str(probe / "vitest.config.mjs"),
             "--reporter=json", f"--outputFile={report}", "--maxWorkers=1"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120,
        )
        print(result.stdout, flush=True)
        assert report.is_file(), (name, result.returncode)
        data = json.loads(report.read_text())
        summary = {key: data[key] for key in ["numTotalTests", "numPassedTests", "numFailedTests", "numPendingTests"]}
        print(name, json.dumps(summary), flush=True)
        if data["numFailedTests"] != failures:
            for suite in data["testResults"]:
                print(suite.get("message", ""), flush=True)
                for result in suite.get("assertionResults", []):
                    if result["status"] == "failed":
                        print(result["fullName"], result.get("failureMessages", []), flush=True)
        assert data["numTotalTests"] == 3
        assert data["numFailedTests"] == failures
        assert data["numPassedTests"] == 3 - failures
        assert data["numPendingTests"] == 0
        assert result.returncode == (1 if failures else 0)

    run("native-directives-present", 0)
    for file, body in bodies.items():
        file.write_text(body)
    run("native-directives-removed", 3)
