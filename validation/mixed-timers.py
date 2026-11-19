import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path.cwd()
package = root / "packages/landmines"
expected = int(sys.argv[1])
with tempfile.TemporaryDirectory(prefix=".mixed-timers-probe-", dir=package) as folder:
    probe = Path(folder)
    filename = probe / "mixed.test.mjs"
    filename.write_text('''import { expect, test, vi } from "vitest";

test("real timer waits still use the native clock", async () => {
  expect(vi.isFakeTimers()).toBe(false);
  await new Promise((resolve) => setTimeout(resolve, 25));
});

test("an independent test advances its own fake clock", async () => {
  vi.useFakeTimers();
  try {
    expect(vi.isFakeTimers()).toBe(true);
    const advance = Promise.resolve().then(() => vi.advanceTimersByTimeAsync(25));
    await new Promise((resolve) => setTimeout(resolve, 25));
    await advance;
  } finally {
    vi.useRealTimers();
  }
});
''')
    config = probe / ".oxlintrc.json"
    config.write_text(json.dumps({
        "categories": {"correctness": "off"},
        "jsPlugins": [{"name": "landmines-testing", "specifier": str(package / "src/plugins/testing.ts")}],
        "rules": {"landmines-testing/no-fixed-sleep": "error"},
    }))
    lint = subprocess.run(
        [str(root / "node_modules/.bin/oxlint"), "--config", str(config), "--threads", "1", str(filename)],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30,
    )
    print(lint.stdout, flush=True)
    count = lint.stdout.count("Replace this fixed sleep with a signal")
    print("mixed-file diagnostics:", count, "expected:", expected, flush=True)
    assert count == expected
    assert lint.returncode == (1 if expected else 0)
    (probe / "vitest.config.mjs").write_text('export default { test: { environment: "node", include: ["*.test.mjs"] } };\n')
    report = Path(os.environ["RUNNER_TEMP"]) / "mixed-timers-native.json"
    result = subprocess.run(
        [str(package / "node_modules/.bin/vitest"), "run", "--root", str(probe),
         "--config", str(probe / "vitest.config.mjs"), "--reporter=json", f"--outputFile={report}", "--maxWorkers=1"],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120,
    )
    print(result.stdout, flush=True)
    assert report.is_file()
    data = json.loads(report.read_text())
    print("real and fake timers runtime:", {key: data[key] for key in ["numTotalTests", "numPassedTests", "numFailedTests", "numPendingTests"]}, flush=True)
    assert result.returncode == 0
    assert data["numTotalTests"] == data["numPassedTests"] == 2
    assert data["numFailedTests"] == data["numPendingTests"] == 0
