# Project Context: Kung Fu Chess
This project is a real-time, highly scalable multiplayer chess variant (Kung Fu Chess) built in Python.
Pieces move in real-time with cooldowns, and the game ends when the King is physically captured.

# Core Architectural & Performance Rules for GitHub Copilot:
1. **Performance First:** Avoid unnecessary loops (`while` or nested `for`), conditions, or repetitive checks. Prefer optimized, native Pythonic operations like slicing, list comprehensions, and built-in methods (which run in C) over manual iteration.
2. **Scalability:** Assume the server must handle millions of concurrent players. Code must be stateless where possible, asynchronous-friendly, and avoid blocking operations.
3. **Design Patterns & SOLID:** Enforce Single Responsibility. Do not write monolithic functions. Use appropriate design patterns (e.g., Strategy Pattern for piece movement, State Pattern for piece statuses like Idle/Jumping/Cooldown) to ensure loose coupling.
4. **No Magic Numbers:** Infer dimensions dynamically where applicable and avoid hardcoded values that break flexibility.
5. **Separation of Concerns:** Keep I/O operations (parsing, printing) completely separate from business logic (validation, game rules). 
6. **Clean Output:** Do not include debugging text, prompts, or explanatory print statements in standard output functions unless explicitly requested.
7. **Clean Code :** Adhere to the rules of Clean Code.

When writing or modifying code, prioritize structural clarity and O(1) or O(n) time complexity where achievable.