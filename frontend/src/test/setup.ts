import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";
import "@testing-library/jest-dom/vitest";

// Testing Library only auto-registers its cleanup when Vitest globals
// are enabled. Globals are off here (tests import describe/it/expect
// explicitly), so unmounting between tests is wired up by hand --
// without it, rendered DOM leaks across tests and text queries start
// matching the previous test's markup.
afterEach(cleanup);
