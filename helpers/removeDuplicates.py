import os
import shutil

INPUT_FILE = "../data.json"
BACKUP_FILE = "../backupForData.json"

def remove_duplicate_top_level_keys_inplace(filename):
    shutil.copy(filename, BACKUP_FILE)
    print(f"Backup created: {BACKUP_FILE}")

    seen_keys = set()
    depth = 0
    in_string = False
    escape = False
    current_string = []
    keep_current_entry = True
    output_lines = []

    with open(filename, "r", encoding="utf-8") as f:
        lines = f.readlines()

    i = 0
    while i < len(lines):
        line = lines[i]
        j = 0
        while j < len(line):
            ch = line[j]
            if in_string:
                if escape:
                    escape = False
                    current_string.append(ch)
                    j += 1
                    continue
                if ch == "\\":
                    escape = True
                    current_string.append(ch)
                    j += 1
                    continue
                if ch == '"':
                    in_string = False
                    collected = "".join(current_string)
                    current_string = []

                    k = j + 1
                    while k < len(line) and line[k].isspace():
                        k += 1
                    if k < len(line) and line[k] == ":" and depth == 1:
                        key_buffer = collected
                        if key_buffer in seen_keys:
                            keep_current_entry = False
                        else:
                            seen_keys.add(key_buffer)
                            keep_current_entry = True
                    j += 1
                    continue
                else:
                    current_string.append(ch)
                    j += 1
                    continue
            else:
                if ch == '"':
                    in_string = True
                    escape = False
                    current_string = []
                    j += 1
                    continue
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth = max(depth - 1, 0)
                j += 1

        if keep_current_entry or depth < 1:
            output_lines.append(line)
        i += 1

    with open(filename, "w", encoding="utf-8") as f:
        f.writelines(output_lines)

    print(f"Cleaned {filename} in-place.")
    print(f"Removed all duplicate top-level keys (kept first occurrence).")
    print(f"Backup saved as {BACKUP_FILE}")

if __name__ == "__main__":
    if not os.path.exists(INPUT_FILE):
        print(f"File not found: {INPUT_FILE}")
    else:
        remove_duplicate_top_level_keys_inplace(INPUT_FILE)
