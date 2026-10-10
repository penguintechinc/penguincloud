/**
 * MSW server setup for jest tests.
 * Wires up request handlers for test environment.
 */

import { setupServer } from "msw/node";
import { handlers } from "./handlers";

export const server = setupServer(...handlers);
