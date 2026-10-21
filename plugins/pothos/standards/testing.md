# Testing standards

Personal standards for automated tests, read by `tdd`, `implement`, `implement-spec` and `code-review`. The repository's own documented conventions win on conflict. Each rule is here because a test suite without it failed in a measured comparison, or because it keeps a suite honest over time.

## Rules

1. **A test you have not seen fail proves nothing.** After green, break the behavior the test names (flip the condition, return the wrong value), watch it fail with a message that names the problem, and restore. Where the repository has a mutation command, the mutation receipt does this for every line you added: a `new` survivor is a missing test or dead code, and a test added to kill it obeys rule 7, so it asserts a value the mutant cannot produce rather than one recomputed from the code. A bug fix starts with the test that reproduces the bug, seen failing on the bug.
2. **When you fix a bug, guard what is next to it.** Add tests for the neighbouring behavior of the code you touched: the other branches of the same function and the paths that share the line you changed. A fix tested only by its own regression test leaves the next change free to break the rest.
3. **Control the clock; never wait for real time.** Debounce, throttle, polling, timeouts and retries run under fake timers, advanced explicitly. Pin both sides of a time rule: nothing at 299 ms, the effect at 300 ms. A test that sleeps is slow, and when the machine is busy it fails.
4. **Settle before asserting that something did not happen.** Wait for the request to finish, or the error to render, before checking that nothing changed. A negative assertion made too early passes while the bug is still there.
5. **Replace only the boundary.** Run your own functions, components, hooks, router, store and query client for real. Fake the network at the request level (a fake server such as MSW), the clock, randomness and third-party services. Force a hard scenario at that boundary (the server answers 500), never by mocking the code in between. Never assert on a library's internal state, such as a query client's mutation cache.
6. **Assert what a person sees or a caller gets.** For a screen, assert on roles, names and visible text. For a function, assert on the return value. For a service, assert on what reached the outside. Never assert on internal state, call order between your own modules, or DOM structure.
7. **Test data is small, fixed and readable.** Build objects with a small builder per domain type, with fixed defaults that cannot cross any rule's threshold, and override only what the test is about. Prefer literal expected values taken from the rule ("a 10 kg cart to Europe costs 19.49") over values recomputed with the code's own formula. Use generated values only where variety matters, with a fixed seed.
8. **Names state the product rule.** Group tests by situation and name each one with the outcome in product words, so the names alone read as the specification. Structure the body as setup, action and check, separated by blank lines. Comment markers are optional.
9. **Each test owns its world.** It gets a fresh client, cache and fake-server handlers, and leaves no shared mutable state. Data is created inside the test. Any test runs alone, in any order.
10. **Size fits the problem.** A pure function needs a table of cases and a builder, not a framework. Add a helper only when a second test needs it. Delete tests that catch nothing another test does not already catch.

## Review questions

For each test: what change breaks it? Does the body prove what the name promises? Is what it replaces really a boundary? Does it pass alone, and on a busy machine?
