/**
 * `OperationsPanel` — the generic panel both Gough's `OperationsPanel` and
 * Nest's `NestOperationsPanel` are now thin adapters over.
 *
 * These tests exercise the kit component in isolation (a product-agnostic
 * `OperationLike` fixture, not `GoughOperation`/`NestOperation`), proving
 * three things the two prior hand-written panels each had to get right on
 * their own: running/succeeded/failed/cancelled render distinguishably (a
 * failed operation can never be read as still running), a failed
 * operation's `error` text is sanitized rather than rendered raw, and the
 * log-stream disclosure only fetches — and only keeps fetching — while an
 * operator actually has it open.
 */
import { act, useEffect, useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { OperationsPanel } from "../OperationsPanel";
import type {
  OperationLike,
  OperationsPanelSpec,
  UseOperationLogsResult,
} from "../operationsPanelTypes";

const BASE_SPEC: OperationsPanelSpec = {
  title: "Operations",
  testIdPrefix: "kit",
  cancelAllowed: true,
  showLogs: true,
  pollIntervalMs: 3000,
};

function operation(overrides: Partial<OperationLike> = {}): OperationLike {
  return {
    id: "op-1",
    kind: "deployment",
    state: "running",
    status: "in_progress",
    is_terminal: false,
    ...overrides,
  };
}

describe("OperationsPanel — empty and loading", () => {
  it("renders nothing when there are no operations", () => {
    render(<OperationsPanel operations={[]} spec={BASE_SPEC} />);
    expect(screen.queryByTestId("kit-operations")).not.toBeInTheDocument();
  });

  it("shows a loading skeleton while the caller's own query is in flight, even with no rows yet", () => {
    render(<OperationsPanel operations={[]} isLoading spec={BASE_SPEC} />);
    expect(screen.getByTestId("kit-operations-loading")).toBeInTheDocument();
    expect(screen.queryByTestId("kit-operations")).not.toBeInTheDocument();
  });

  it("marks the section aria-live so a poll updating it is announced", () => {
    render(<OperationsPanel operations={[operation()]} spec={BASE_SPEC} />);
    expect(screen.getByTestId("kit-operations")).toHaveAttribute(
      "aria-live",
      "polite",
    );
  });
});

describe("OperationsPanel — state distinguishability", () => {
  it.each([
    ["running", "in_progress"],
    ["succeeded", "Succeeded"],
    ["failed", "Failed"],
    ["cancelled", "Cancelled"],
    ["pending", "Queued"],
  ])("renders the %s state's own status text", (state, status) => {
    render(
      <OperationsPanel
        operations={[
          operation({
            state,
            status,
            is_terminal: state !== "running" && state !== "pending",
          }),
        ]}
        spec={BASE_SPEC}
      />,
    );
    expect(screen.getByTestId("kit-operation-state-op-1")).toHaveTextContent(
      status,
    );
  });

  // Injection-prove the terminal-vs-running distinction: a failed operation
  // sitting alongside a genuinely running one must not be offered the same
  // "still in progress" affordance (a cancel control) a running one gets —
  // that IS the class of bug ("silence reads as success", or here "a
  // spinner that never resolves") this migration keeps closing.
  it("never offers cancel on a failed operation, unlike a running one in the same panel", () => {
    render(
      <OperationsPanel
        operations={[
          operation({
            id: "op-running",
            state: "running",
            status: "in_progress",
            is_terminal: false,
          }),
          operation({
            id: "op-failed",
            state: "failed",
            status: "Failed",
            is_terminal: true,
            error: "deploy failed",
          }),
        ]}
        spec={BASE_SPEC}
        onCancel={jest.fn()}
      />,
    );

    expect(
      screen.getByTestId("kit-operation-cancel-op-running"),
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId("kit-operation-cancel-op-failed"),
    ).not.toBeInTheDocument();
    expect(
      screen.getByTestId("kit-operation-error-op-failed"),
    ).toHaveTextContent("deploy failed");
  });

  it("falls back to the raw state and a neutral badge class for a state the badge doesn't recognise", () => {
    // A product vocabulary the adapter hasn't mapped a colour for yet must
    // still read as something, not throw or render blank.
    render(
      <OperationsPanel
        operations={[operation({ state: "retrying", status: "" })]}
        spec={BASE_SPEC}
      />,
    );
    expect(screen.getByTestId("kit-operation-state-op-1")).toHaveTextContent(
      "retrying",
    );
  });
});

describe("OperationsPanel — error sanitization", () => {
  it("shows a short, structured failure reason verbatim", () => {
    render(
      <OperationsPanel
        operations={[
          operation({
            state: "failed",
            is_terminal: true,
            error: "nest.migrate.source_unreachable",
          }),
        ]}
        spec={BASE_SPEC}
      />,
    );
    expect(screen.getByTestId("kit-operation-error-op-1")).toHaveTextContent(
      "nest.migrate.source_unreachable",
    );
  });

  it("never renders a dumped-exception-shaped error verbatim", () => {
    const leaky =
      "HTTPConnectionPool(host='gough-api-primary.penguincloud-prod.svc.cluster.local', " +
      "port=8080): Max retries exceeded with url: /v1/nodes/42/deploy " +
      "(Caused by NewConnectionError('<urllib3.connection.HTTPConnection object>: " +
      "Failed to establish a new connection: [Errno 111] Connection refused'))";
    render(
      <OperationsPanel
        operations={[
          operation({ state: "failed", is_terminal: true, error: leaky }),
        ]}
        spec={BASE_SPEC}
      />,
    );
    const rendered = screen.getByTestId("kit-operation-error-op-1");
    expect(rendered).not.toHaveTextContent("gough-api-primary");
    expect(rendered).not.toHaveTextContent("penguincloud-prod");
    expect(rendered.textContent).toBe(
      "This operation failed. Try again, or contact support if this continues.",
    );
  });

  it("renders no error node at all when the operation has none", () => {
    render(<OperationsPanel operations={[operation()]} spec={BASE_SPEC} />);
    expect(
      screen.queryByTestId("kit-operation-error-op-1"),
    ).not.toBeInTheDocument();
  });
});

describe("OperationsPanel — cancel", () => {
  it("calls onCancel with the operation when clicked", () => {
    const onCancel = jest.fn();
    render(
      <OperationsPanel
        operations={[operation()]}
        spec={BASE_SPEC}
        onCancel={onCancel}
      />,
    );
    fireEvent.click(screen.getByTestId("kit-operation-cancel-op-1"));
    expect(onCancel).toHaveBeenCalledWith(operation());
  });

  it("offers no cancel control at all when the spec disallows it", () => {
    render(
      <OperationsPanel
        operations={[operation()]}
        spec={{ ...BASE_SPEC, cancelAllowed: false }}
        onCancel={jest.fn()}
      />,
    );
    expect(
      screen.queryByTestId("kit-operation-cancel-op-1"),
    ).not.toBeInTheDocument();
  });

  it("disables cancel while isCancelling reports true", () => {
    render(
      <OperationsPanel
        operations={[operation()]}
        spec={BASE_SPEC}
        onCancel={jest.fn()}
        isCancelling={() => true}
      />,
    );
    expect(screen.getByTestId("kit-operation-cancel-op-1")).toBeDisabled();
  });
});

describe("OperationsPanel — progress", () => {
  it("invents no progress bar when progress is null", () => {
    render(
      <OperationsPanel
        operations={[operation({ progress: null })]}
        spec={BASE_SPEC}
      />,
    );
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });

  it("renders a real fraction as a progress bar", () => {
    render(
      <OperationsPanel
        operations={[operation({ progress: 0.5 })]}
        spec={BASE_SPEC}
      />,
    );
    expect(screen.getByRole("progressbar")).toHaveAttribute(
      "aria-valuenow",
      "50",
    );
  });
});

describe("OperationsPanel — result", () => {
  it("renders what a succeeded operation produced", () => {
    render(
      <OperationsPanel
        operations={[
          operation({
            state: "succeeded",
            status: "Succeeded",
            is_terminal: true,
            result: { snapshotName: "orders-primary-snap-1" },
          }),
        ]}
        spec={BASE_SPEC}
      />,
    );
    expect(screen.getByText("orders-primary-snap-1")).toBeInTheDocument();
  });

  it("renders an object-valued result entry as its JSON representation", () => {
    render(
      <OperationsPanel
        operations={[
          operation({
            state: "succeeded",
            status: "Succeeded",
            is_terminal: true,
            result: { report: { restored: 3, skipped: 1 } },
          }),
        ]}
        spec={BASE_SPEC}
      />,
    );
    expect(
      screen.getByText(JSON.stringify({ restored: 3, skipped: 1 })),
    ).toBeInTheDocument();
  });

  it("renders nothing when the result has no non-empty entries", () => {
    render(
      <OperationsPanel
        operations={[
          operation({
            state: "succeeded",
            status: "Succeeded",
            is_terminal: true,
            result: { note: null, label: "" },
          }),
        ]}
        spec={BASE_SPEC}
      />,
    );
    expect(screen.queryByText("note")).not.toBeInTheDocument();
    expect(screen.queryByText("label")).not.toBeInTheDocument();
  });
});

describe("OperationsPanel — logs disclosure", () => {
  function logsResult(overrides: Partial<UseOperationLogsResult> = {}) {
    return { data: undefined, isLoading: false, error: null, ...overrides };
  }

  it("offers no logs toggle when the spec disallows it, even with a hook supplied", () => {
    render(
      <OperationsPanel
        operations={[operation()]}
        spec={{ ...BASE_SPEC, showLogs: false }}
        useOperationLogs={jest.fn(() => logsResult())}
      />,
    );
    expect(
      screen.queryByTestId("kit-operation-logs-toggle-op-1"),
    ).not.toBeInTheDocument();
  });

  it("does not fetch logs until the operator opens them", () => {
    const hook = jest.fn(() => logsResult());
    render(
      <OperationsPanel
        operations={[operation()]}
        spec={BASE_SPEC}
        useOperationLogs={hook}
      />,
    );
    expect(
      screen.getByTestId("kit-operation-logs-toggle-op-1"),
    ).toHaveAttribute("aria-expanded", "false");
    expect(hook).not.toHaveBeenCalled();
  });

  it("fetches with the operation's kind, id, and terminal state once opened", () => {
    const hook = jest.fn(() => logsResult());
    render(
      <OperationsPanel
        operations={[
          operation({
            kind: "biome_upgrade",
            is_terminal: true,
            state: "failed",
          }),
        ]}
        spec={BASE_SPEC}
        useOperationLogs={hook}
      />,
    );
    fireEvent.click(screen.getByTestId("kit-operation-logs-toggle-op-1"));
    expect(hook).toHaveBeenCalledWith("biome_upgrade", "op-1", {
      enabled: true,
      isTerminal: true,
    });
  });

  it("renders a loading skeleton while the log fetch is in flight", () => {
    render(
      <OperationsPanel
        operations={[operation()]}
        spec={BASE_SPEC}
        useOperationLogs={() => logsResult({ isLoading: true })}
      />,
    );
    fireEvent.click(screen.getByTestId("kit-operation-logs-toggle-op-1"));
    expect(
      screen.getByTestId("kit-operation-logs-loading-op-1"),
    ).toBeInTheDocument();
  });

  it("surfaces a log fetch failure rather than an empty stream", () => {
    render(
      <OperationsPanel
        operations={[operation()]}
        spec={BASE_SPEC}
        useOperationLogs={() => logsResult({ error: new Error("nope") })}
      />,
    );
    fireEvent.click(screen.getByTestId("kit-operation-logs-toggle-op-1"));
    expect(
      screen.getByTestId("kit-operation-logs-error-op-1"),
    ).toBeInTheDocument();
  });

  it("reports an empty stream rather than rendering nothing", () => {
    render(
      <OperationsPanel
        operations={[operation()]}
        spec={BASE_SPEC}
        useOperationLogs={() => logsResult({ data: [] })}
      />,
    );
    fireEvent.click(screen.getByTestId("kit-operation-logs-toggle-op-1"));
    expect(
      screen.getByTestId("kit-operation-logs-empty-op-1"),
    ).toBeInTheDocument();
  });

  it("renders populated log lines", () => {
    render(
      <OperationsPanel
        operations={[operation()]}
        spec={BASE_SPEC}
        useOperationLogs={() =>
          logsResult({
            data: [
              {
                timestamp: "2026-08-08T00:00:00Z",
                level: "info",
                message: "started",
              },
              {
                timestamp: "2026-08-08T00:00:05Z",
                level: "error",
                message: "boom",
              },
              // No timestamp, no level, and an unrecognised level: the wire
              // contract makes both optional and doesn't constrain level's
              // vocabulary, so a line missing either must still render.
              { message: "no timestamp or level" },
              { level: "trace", message: "unrecognised level" },
            ],
          })
        }
      />,
    );
    fireEvent.click(screen.getByTestId("kit-operation-logs-toggle-op-1"));
    expect(screen.getByText("started")).toBeInTheDocument();
    expect(screen.getByText("boom")).toBeInTheDocument();
    expect(screen.getByText("no timestamp or level")).toBeInTheDocument();
    expect(screen.getByText("unrecognised level")).toBeInTheDocument();
  });

  it("closing the disclosure unmounts the log view (aria-expanded returns to false)", () => {
    render(
      <OperationsPanel
        operations={[operation()]}
        spec={BASE_SPEC}
        useOperationLogs={() => logsResult({ data: [] })}
      />,
    );
    const toggle = screen.getByTestId("kit-operation-logs-toggle-op-1");
    fireEvent.click(toggle);
    expect(
      screen.getByTestId("kit-operation-logs-empty-op-1"),
    ).toBeInTheDocument();

    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(
      screen.queryByTestId("kit-operation-logs-empty-op-1"),
    ).not.toBeInTheDocument();
  });

  // The concrete "no timer leak on unmount" proof: a hook shaped like a real
  // data-fetching one (owns an interval, clears it on its own unmount) must
  // actually be torn down when the panel unmounts with logs open — which
  // only happens if the kit's conditional-mount structure (`showLogs &&
  // <OperationLogsSection .../>`) genuinely unmounts that subtree rather
  // than merely hiding it.
  it("tears down an in-flight log poll when the panel unmounts while logs are open", () => {
    const clearSpy = jest.spyOn(window, "clearInterval");

    function useFakePollingLogs(): UseOperationLogsResult {
      const [data, setData] =
        useState<UseOperationLogsResult["data"]>(undefined);
      useEffect(() => {
        const id = setInterval(() => {
          setData([{ message: "tick" }]);
        }, 1000);
        return () => clearInterval(id);
      }, []);
      return { data, isLoading: false, error: null };
    }

    const { unmount } = render(
      <OperationsPanel
        operations={[operation()]}
        spec={BASE_SPEC}
        useOperationLogs={useFakePollingLogs}
      />,
    );
    fireEvent.click(screen.getByTestId("kit-operation-logs-toggle-op-1"));

    act(() => {
      unmount();
    });

    expect(clearSpy).toHaveBeenCalled();
    clearSpy.mockRestore();
  });
});
