import { render, screen, fireEvent } from "@testing-library/react";
import { DetailDrawer } from "../DetailDrawer";

const tabs = [
  { id: "overview", label: "Overview", content: <p>Overview body</p> },
  { id: "logs", label: "Logs", content: <p>Logs body</p> },
];

function setup(overrides: Record<string, unknown> = {}) {
  const onClose = jest.fn();
  const onTabChange = jest.fn();
  render(
    <DetailDrawer
      isOpen
      title="Node 12"
      subtitle="rack-a"
      tabs={tabs}
      activeTab="overview"
      onTabChange={onTabChange}
      onClose={onClose}
      {...overrides}
    />,
  );
  return { onClose, onTabChange };
}

describe("DetailDrawer", () => {
  it("does not render when closed", () => {
    render(
      <DetailDrawer
        isOpen={false}
        title="Node 12"
        tabs={tabs}
        activeTab="overview"
        onTabChange={jest.fn()}
        onClose={jest.fn()}
      />,
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("renders the title, subtitle and the active tab's content", () => {
    setup();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("Node 12")).toBeInTheDocument();
    expect(screen.getByText("rack-a")).toBeInTheDocument();
    expect(screen.getByText("Overview body")).toBeInTheDocument();
    expect(screen.queryByText("Logs body")).not.toBeInTheDocument();
  });

  it("marks only the active tab as selected", () => {
    setup();
    expect(screen.getByTestId("detail-drawer-tab-overview")).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByTestId("detail-drawer-tab-logs")).toHaveAttribute(
      "aria-selected",
      "false",
    );
  });

  it("reports a tab change rather than owning the state", () => {
    const { onTabChange } = setup();
    fireEvent.click(screen.getByTestId("detail-drawer-tab-logs"));
    expect(onTabChange).toHaveBeenCalledWith("logs");
  });

  it("closes on the close button, the backdrop and Escape", () => {
    const { onClose } = setup();

    fireEvent.click(screen.getByTestId("detail-drawer-close"));
    fireEvent.click(screen.getByTestId("detail-drawer-backdrop"));
    fireEvent.keyDown(document, { key: "Escape" });

    expect(onClose).toHaveBeenCalledTimes(3);
  });

  it("ignores unrelated keys", () => {
    const { onClose } = setup();
    fireEvent.keyDown(document, { key: "a" });
    expect(onClose).not.toHaveBeenCalled();
  });

  it("focuses the close button so a keyboard user is not stranded", () => {
    setup();
    expect(screen.getByTestId("detail-drawer-close")).toHaveFocus();
  });

  it("hides the tablist when there is only one tab", () => {
    setup({ tabs: [tabs[0]] });
    expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
    expect(screen.getByText("Overview body")).toBeInTheDocument();
  });

  it("falls back to the first tab when activeTab names nothing", () => {
    // A caller can hold a stale tab id after the tab set changes; rendering
    // an empty panel would look like a data failure.
    setup({ activeTab: "gone" });
    expect(screen.getByText("Overview body")).toBeInTheDocument();
  });

  it("omits the subtitle and footer when not supplied", () => {
    setup({ subtitle: undefined });
    expect(screen.queryByText("rack-a")).not.toBeInTheDocument();
  });

  it("renders footer actions when supplied", () => {
    setup({ actions: <button type="button">Deploy</button> });
    expect(screen.getByText("Deploy")).toBeInTheDocument();
  });

  it("honours a custom testId", () => {
    setup({ testId: "gough-node-drawer" });
    expect(screen.getByTestId("gough-node-drawer")).toBeInTheDocument();
  });

  it("detaches its key listener on unmount", () => {
    const onClose = jest.fn();
    const { unmount } = render(
      <DetailDrawer
        isOpen
        title="T"
        tabs={tabs}
        activeTab="overview"
        onTabChange={jest.fn()}
        onClose={onClose}
      />,
    );
    unmount();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).not.toHaveBeenCalled();
  });
});
