// Testing Library cleans up after each test only when test globals are on; they are not.
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => {
  cleanup();
});
