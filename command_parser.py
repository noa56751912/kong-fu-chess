def parse_commands(input_text):
    lines = input_text.splitlines()
    commands = []
    in_commands = False
    for line in lines:
        if line.strip() == 'Commands:':
            in_commands = True
            continue
        if not in_commands:
            continue
        stripped = line.strip()
        if not stripped:
            continue
        if stripped == 'print board':
            commands.append(('print_board',))
        elif stripped.startswith('wait '):
            parts = stripped.split()
            if len(parts) != 2 or not parts[1].isdigit():
                raise ValueError("ERROR UNKNOWN_TOKEN")
            commands.append(('wait', int(parts[1])))
        elif stripped.startswith('click '):
            parts = stripped.split()
            if len(parts) != 3 or not parts[1].lstrip('-').isdigit() or not parts[2].lstrip('-').isdigit():
                raise ValueError("ERROR UNKNOWN_TOKEN")
            commands.append(('click', int(parts[1]), int(parts[2])))
        else:
            raise ValueError("ERROR UNKNOWN_TOKEN")
    return commands
