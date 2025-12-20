import sys
import os
from collections import defaultdict

FILENAME = "../data.json"

def find_top_level_key_duplicates(filename):
    seen = {}
    duplicates = defaultdict(list)

    depth = 0
    in_string = False
    escape = False
    current_string = []
    with open(filename, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            i = 0
            while i < len(line):
                ch = line[i]

                if in_string:
                    if escape:
                        escape = False
                        current_string.append(ch)
                        i += 1
                        continue
                    if ch == "\\":
                        escape = True
                        current_string.append(ch)
                        i += 1
                        continue
                    if ch == '"':
                        in_string = False
                        collected = "".join(current_string)
                        j = i + 1
                        while j < len(line) and line[j].isspace():
                            j += 1
                        if j < len(line) and line[j] == ":" and depth == 1:
                            key = collected
                            if key in seen:
                                duplicates[key].append(lineno)
                            else:
                                seen[key] = lineno
                        current_string = []
                        i += 1
                        continue
                    else:
                        current_string.append(ch)
                        i += 1
                        continue

                else:
                    if ch == '"':
                        in_string = True
                        escape = False
                        current_string = []
                        i += 1
                        continue
                    if ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth = max(depth - 1, 0)
                    i += 1

    return seen, duplicates

if __name__ == "__main__":
    if not os.path.exists(FILENAME):
        print(f"File not found: {FILENAME}")
        sys.exit(1)

    seen, duplicates = find_top_level_key_duplicates(FILENAME)

    if not duplicates:
        print("No duplicate top-level keys found.")
    else:
        print("Duplicate top-level keys found:\n")
        for key, lines in duplicates.items():
            first = seen.get(key, "?")
            print(f"Key '{key}' first seen at line {first}, duplicates at lines: {', '.join(map(str, lines))}")
