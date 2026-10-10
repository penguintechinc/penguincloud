/**
 * The three atoms promoted out of the Gough and Nest page directories.
 *
 * Both copies carried the same note: the duplication was bounded, and on a
 * third product they belonged in the kit "where the variant styles and the
 * absent-value rendering can be asserted once". Tobogganing is that third
 * product, and this file is the "asserted once" half — previously neither copy
 * had a test of its own, so the danger styling and the dash-for-absent
 * rendering were only ever exercised incidentally through a page test.
 */

import { render, screen, fireEvent, within } from "@testing-library/react";
import { ActionButton } from "../ActionButton";
import { FactList } from "../FactList";
import { RowOpenButtons } from "../RowOpenButtons";

describe("ActionButton", () => {
  it("renders its label and reports clicks", () => {
    const onClick = jest.fn();

    render(<ActionButton label="Publish" onClick={onClick} testId="publish" />);
    fireEvent.click(screen.getByTestId("publish"));

    expect(screen.getByTestId("publish")).toHaveTextContent("Publish");
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("styles a danger verb differently from a primary one", () => {
    // The whole reason this is a component rather than a className. A danger
    // verb that renders identically to "open details" is the defect; asserting
    // "has some class" would pass for that, so the two are compared.
    render(
      <>
        <ActionButton label="Open" onClick={jest.fn()} testId="safe" />
        <ActionButton
          label="Delete"
          onClick={jest.fn()}
          testId="danger"
          variant="danger"
        />
      </>,
    );

    const safe = screen.getByTestId("safe").className;
    const danger = screen.getByTestId("danger").className;

    expect(danger).not.toEqual(safe);
    expect(danger).toContain("bg-red-600");
    expect(safe).toContain("bg-sky-500");
  });

  it("does not fire when disabled", () => {
    const onClick = jest.fn();

    render(
      <ActionButton label="Apply" onClick={onClick} testId="apply" disabled />,
    );
    fireEvent.click(screen.getByTestId("apply"));

    expect(screen.getByTestId("apply")).toBeDisabled();
    expect(onClick).not.toHaveBeenCalled();
  });

  it("is keyboard reachable and carries an explicit type", () => {
    // `type="button"` matters: inside a form the default is submit, which turns
    // "Preview" into "save the form" on the first screen that wraps one.
    render(<ActionButton label="Preview" onClick={jest.fn()} testId="prev" />);

    const button = screen.getByTestId("prev");
    button.focus();

    expect(button).toHaveAttribute("type", "button");
    expect(button).toHaveFocus();
  });
});

describe("FactList", () => {
  it("renders a dash for every absent value rather than a blank cell", () => {
    // A blank cell reads as a layout bug. A dash reads as "the product did not
    // report one", which is the true statement — and is the single behaviour
    // both former copies existed to keep consistent.
    render(
      <FactList
        testId="facts"
        facts={[
          ["Present", "value"],
          ["Null", null],
          ["Undefined", undefined],
          ["Empty", ""],
        ]}
      />,
    );

    const facts = within(screen.getByTestId("facts"));
    expect(facts.getByText("value")).toBeInTheDocument();
    expect(facts.getAllByText("—")).toHaveLength(3);
  });

  it("keys each product's list separately", () => {
    // `testId` is required, not defaulted: the two former copies hardcoded
    // `gough-facts` and `nest-facts`, and a shared default would make two
    // lists on one screen indistinguishable to a test.
    render(
      <>
        <FactList testId="gough-facts" facts={[["A", "1"]]} />
        <FactList testId="nest-facts" facts={[["B", "2"]]} />
      </>,
    );

    expect(
      within(screen.getByTestId("gough-facts")).getByText("1"),
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId("nest-facts")).getByText("2"),
    ).toBeInTheDocument();
  });
});

describe("RowOpenButtons", () => {
  const rows = [
    { id: "a", name: "alpha" },
    { id: "b", name: "beta" },
  ];

  it("renders one focusable button per row and reports which was opened", () => {
    // Buttons rather than a clickable <tr>: a row-wide click target is
    // unreachable by keyboard, which would make every drawer mouse-only.
    const onOpen = jest.fn();

    render(
      <RowOpenButtons
        rows={rows}
        label={(row) => row.name}
        onOpen={onOpen}
        testIdPrefix="open"
      />,
    );
    const second = screen.getByTestId("open-b");
    second.focus();
    fireEvent.click(second);

    expect(second.tagName).toBe("BUTTON");
    expect(second).toHaveFocus();
    expect(onOpen).toHaveBeenCalledWith(rows[1]);
  });

  it("renders nothing for an empty row set", () => {
    render(
      <RowOpenButtons
        rows={[]}
        label={(row: { id: string }) => row.id}
        onOpen={jest.fn()}
        testIdPrefix="open"
      />,
    );

    expect(screen.queryByTestId(/^open-/)).not.toBeInTheDocument();
  });
});
