"""Turn a pytest junit report into the run summary GitHub shows on the job.

Keeps the failure list readable without opening the raw log.
"""

import sys
import xml.etree.ElementTree as ET


def main(path):
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        print(f"Could not read the test report: {exc}")
        return 0

    suite = root.find("testsuite") if root.tag == "testsuites" else root
    if suite is None:
        print("No test results found.")
        return 0

    total = int(suite.get("tests", 0))
    failures = int(suite.get("failures", 0))
    errors = int(suite.get("errors", 0))
    skipped = int(suite.get("skipped", 0))
    passed = total - failures - errors - skipped
    seconds = float(suite.get("time", 0))

    mark = "x" if failures or errors else "check"
    print(f"## Tests {'failed' if mark == 'x' else 'passed'}")
    print()
    print("| Passed | Failed | Errors | Skipped | Time |")
    print("| --- | --- | --- | --- | --- |")
    print(f"| {passed} | {failures} | {errors} | {skipped} | {seconds:.1f}s |")

    broken = [
        case
        for case in suite.iter("testcase")
        if case.find("failure") is not None or case.find("error") is not None
    ]
    if not broken:
        return 0

    print()
    print("### What failed")
    print()
    for case in broken:
        problem = case.find("failure")
        if problem is None:
            problem = case.find("error")
        message = (problem.get("message") or "").strip().splitlines()
        first_line = message[0] if message else "no message"
        print(f"- `{case.get('classname')}::{case.get('name')}` {first_line[:200]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "results.xml"))
