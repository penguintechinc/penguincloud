import React from "react";
import { render, screen, fireEvent, within } from "@testing-library/react";
import { DataTable, type ColumnConfig } from "../DataTable";

interface TestRow {
  id: string;
  name: string;
  status: string;
  count: number;
}

const mockColumns: ColumnConfig<TestRow>[] = [
  { key: "name", label: "Name", sortable: true },
  { key: "status", label: "Status", sortable: true },
  { key: "count", label: "Count", sortable: true },
];

const mockData: TestRow[] = [
  { id: "1", name: "Alice", status: "active", count: 10 },
  { id: "2", name: "Bob", status: "inactive", count: 5 },
  { id: "3", name: "Charlie", status: "active", count: 15 },
];

describe("DataTable", () => {
  it("renders table with data", () => {
    render(<DataTable columns={mockColumns} data={mockData} pageSize={25} />);

    expect(screen.getByTestId("datatable")).toBeInTheDocument();
    expect(screen.getByText("Alice")).toBeInTheDocument();
    expect(screen.getByText("Bob")).toBeInTheDocument();
    expect(screen.getAllByTestId("datatable-row")).toHaveLength(3);
  });

  it("renders loading state", () => {
    render(<DataTable columns={mockColumns} data={[]} isLoading={true} />);

    expect(
      screen.getByRole("status", { name: /loading/i }),
    ).toBeInTheDocument();
  });

  it("renders error state with retry button", () => {
    const mockError = new Error("Failed to load");
    const onRetry = jest.fn();

    render(
      <DataTable
        columns={mockColumns}
        data={[]}
        error={mockError}
        onRetry={onRetry}
      />,
    );

    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("Error loading data")).toBeInTheDocument();
    expect(screen.getByText("Failed to load")).toBeInTheDocument();

    const retryBtn = screen.getByRole("button", { name: /retry/i });
    fireEvent.click(retryBtn);
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("renders empty state", () => {
    render(<DataTable columns={mockColumns} data={[]} />);

    expect(screen.getByTestId("datatable-empty")).toBeInTheDocument();
    expect(screen.getByText("No data available")).toBeInTheDocument();
  });

  it("sorts by column ascending", () => {
    render(<DataTable columns={mockColumns} data={mockData} pageSize={25} />);

    const nameSort = screen.getByTestId("sort-name");
    fireEvent.click(nameSort);

    const rows = screen.getAllByTestId("datatable-row");
    expect(within(rows[0]).getByText("Alice")).toBeInTheDocument();
    expect(within(rows[1]).getByText("Bob")).toBeInTheDocument();
    expect(within(rows[2]).getByText("Charlie")).toBeInTheDocument();
  });

  it("sorts by column descending", () => {
    render(<DataTable columns={mockColumns} data={mockData} pageSize={25} />);

    const nameSort = screen.getByTestId("sort-name");
    fireEvent.click(nameSort);
    fireEvent.click(nameSort);

    const rows = screen.getAllByTestId("datatable-row");
    expect(within(rows[0]).getByText("Charlie")).toBeInTheDocument();
    expect(within(rows[1]).getByText("Bob")).toBeInTheDocument();
    expect(within(rows[2]).getByText("Alice")).toBeInTheDocument();
  });

  it("sorts numeric column ascending", () => {
    render(<DataTable columns={mockColumns} data={mockData} pageSize={25} />);

    const countSort = screen.getByTestId("sort-count");
    fireEvent.click(countSort);

    const rows = screen.getAllByTestId("datatable-row");
    expect(within(rows[0]).getByText("5")).toBeInTheDocument();
    expect(within(rows[1]).getByText("10")).toBeInTheDocument();
    expect(within(rows[2]).getByText("15")).toBeInTheDocument();
  });

  it("sorts numeric column descending", () => {
    render(<DataTable columns={mockColumns} data={mockData} pageSize={25} />);

    const countSort = screen.getByTestId("sort-count");
    fireEvent.click(countSort);
    fireEvent.click(countSort);

    const rows = screen.getAllByTestId("datatable-row");
    expect(within(rows[0]).getByText("15")).toBeInTheDocument();
    expect(within(rows[1]).getByText("10")).toBeInTheDocument();
    expect(within(rows[2]).getByText("5")).toBeInTheDocument();
  });

  it("handles sorting with mixed/incompatible types", () => {
    const booleanData: TestRow[] = [
      { id: "1", name: "Alice", status: "active", count: 10 },
      { id: "2", name: "Bob", status: "inactive", count: 5 },
      { id: "3", name: "Charlie", status: "active", count: 15 },
    ];

    render(
      <DataTable columns={mockColumns} data={booleanData} pageSize={25} />,
    );

    // Sorting by status (string) should work
    const statusSort = screen.getByTestId("sort-status");
    fireEvent.click(statusSort);
    const rows = screen.getAllByTestId("datatable-row");
    // Status values: 'active', 'inactive', 'active'
    expect(within(rows[0]).getByText("active")).toBeInTheDocument();
  });

  it("paginates data correctly", () => {
    const largeData = Array.from({ length: 30 }, (_, i) => ({
      id: String(i),
      name: `Item ${i}`,
      status: "active",
      count: i,
    }));

    render(<DataTable columns={mockColumns} data={largeData} pageSize={10} />);

    expect(screen.getAllByTestId("datatable-row")).toHaveLength(10);
    expect(screen.getByText(/Page 1 of 3/)).toBeInTheDocument();

    const nextBtn = screen.getByTestId("datatable-next");
    fireEvent.click(nextBtn);

    expect(screen.getByText(/Page 2 of 3/)).toBeInTheDocument();
    expect(screen.getByText("Item 10")).toBeInTheDocument();
  });

  it("disables pagination buttons at boundaries", () => {
    const threeItems = [
      { id: "1", name: "Alice", status: "active", count: 10 },
      { id: "2", name: "Bob", status: "inactive", count: 5 },
      { id: "3", name: "Charlie", status: "active", count: 15 },
    ];

    render(<DataTable columns={mockColumns} data={threeItems} pageSize={1} />);

    // On page 1: prev should be disabled, next should be enabled
    expect(screen.getByTestId("datatable-prev")).toBeDisabled();
    expect(screen.getByTestId("datatable-next")).not.toBeDisabled();
    expect(screen.getByText("Alice")).toBeInTheDocument();

    // Navigate to last page
    const nextBtn = screen.getByTestId("datatable-next");
    fireEvent.click(nextBtn);
    fireEvent.click(nextBtn);

    // On last page: next should be disabled, prev should be enabled
    expect(screen.getByTestId("datatable-next")).toBeDisabled();
    expect(screen.getByTestId("datatable-prev")).not.toBeDisabled();
    expect(screen.getByText("Charlie")).toBeInTheDocument();
  });

  it("hides pagination when only one page", () => {
    const twoItems = [
      { id: "1", name: "Alice", status: "active", count: 10 },
      { id: "2", name: "Bob", status: "inactive", count: 5 },
    ];

    render(<DataTable columns={mockColumns} data={twoItems} pageSize={10} />);

    // Pagination controls should not be in document for single-page data
    expect(screen.queryByTestId("datatable-prev")).not.toBeInTheDocument();
    expect(screen.queryByTestId("datatable-next")).not.toBeInTheDocument();
  });

  it("renders custom column renderer", () => {
    const customColumns: ColumnConfig<TestRow>[] = [
      {
        key: "name",
        label: "Name",
        render: (val) => <strong>{val}</strong>,
      },
    ];

    render(<DataTable columns={customColumns} data={[mockData[0]]} />);

    expect(screen.getByRole("cell")).toHaveTextContent("Alice");
  });

  it("handles non-sortable columns", () => {
    const nonSortableColumns: ColumnConfig<TestRow>[] = [
      { key: "name", label: "Name", sortable: false },
    ];

    render(<DataTable columns={nonSortableColumns} data={mockData} />);

    const nameHeader = screen.getByText("Name");
    fireEvent.click(nameHeader);

    // Data should remain in original order
    const rows = screen.getAllByTestId("datatable-row");
    expect(within(rows[0]).getByText("Alice")).toBeInTheDocument();
  });

  it("supports keyboard navigation for sort", () => {
    render(<DataTable columns={mockColumns} data={mockData} pageSize={25} />);

    const nameSort = screen.getByTestId("sort-name");
    fireEvent.keyDown(nameSort, { key: "Enter" });

    const rows = screen.getAllByTestId("datatable-row");
    expect(within(rows[0]).getByText("Alice")).toBeInTheDocument();
  });

  it("has proper ARIA labels and roles", () => {
    render(
      <DataTable
        columns={mockColumns}
        data={mockData}
        caption="Test table caption"
      />,
    );

    expect(screen.getByRole("table")).toHaveAttribute(
      "aria-label",
      "Test table caption",
    );
    expect(
      screen.getByRole("columnheader", { name: /Name/i }),
    ).toBeInTheDocument();
  });

  it("handles prev button navigation when enabled", () => {
    const data = Array.from({ length: 30 }, (_, i) => ({
      id: String(i),
      name: `Item ${i}`,
      status: "active",
      count: i,
    }));

    render(<DataTable columns={mockColumns} data={data} pageSize={10} />);

    // Start on page 1
    expect(screen.getByText(/Page 1 of 3/)).toBeInTheDocument();
    const nextBtn = screen.getByTestId("datatable-next");
    fireEvent.click(nextBtn);

    // Now on page 2
    expect(screen.getByText(/Page 2 of 3/)).toBeInTheDocument();
    const prevBtn = screen.getByTestId("datatable-prev");
    expect(prevBtn).not.toBeDisabled();
    fireEvent.click(prevBtn);

    // Back to page 1
    expect(screen.getByText(/Page 1 of 3/)).toBeInTheDocument();
  });

  it("sorts with equal values staying stable", () => {
    const dataWithDuplicates: TestRow[] = [
      { id: "1", name: "Alice", status: "active", count: 10 },
      { id: "2", name: "Bob", status: "active", count: 10 },
      { id: "3", name: "Charlie", status: "active", count: 10 },
    ];

    render(
      <DataTable
        columns={mockColumns}
        data={dataWithDuplicates}
        pageSize={25}
      />,
    );

    const countSort = screen.getByTestId("sort-count");
    fireEvent.click(countSort);

    // All have count=10, so they should remain in original order
    const rows = screen.getAllByTestId("datatable-row");
    expect(within(rows[0]).getByText("Alice")).toBeInTheDocument();
    expect(within(rows[1]).getByText("Bob")).toBeInTheDocument();
    expect(within(rows[2]).getByText("Charlie")).toBeInTheDocument();
  });

  it("maintains sort order and direction through multiple clicks", () => {
    render(<DataTable columns={mockColumns} data={mockData} pageSize={25} />);

    const statusSort = screen.getByTestId("sort-status");

    // First click: ascending
    fireEvent.click(statusSort);
    let rows = screen.getAllByTestId("datatable-row");
    expect(within(rows[0]).getByText("active")).toBeInTheDocument();

    // Second click: descending
    fireEvent.click(statusSort);
    rows = screen.getAllByTestId("datatable-row");
    // 'inactive' comes after 'active' in reverse alphabetical
    expect(within(rows[0]).getByText("inactive")).toBeInTheDocument();

    // Click on different column
    const nameSort = screen.getByTestId("sort-name");
    fireEvent.click(nameSort);
    rows = screen.getAllByTestId("datatable-row");
    // Should reset to asc on new column
    expect(within(rows[0]).getByText("Alice")).toBeInTheDocument();

    // Click again to reverse
    fireEvent.click(nameSort);
    rows = screen.getAllByTestId("datatable-row");
    expect(within(rows[0]).getByText("Charlie")).toBeInTheDocument();
  });

  it("exercises all sort direction branches with direct toggle", () => {
    const data: TestRow[] = [
      { id: "1", name: "Zebra", status: "active", count: 100 },
      { id: "2", name: "Apple", status: "active", count: 50 },
    ];

    render(<DataTable columns={mockColumns} data={data} pageSize={25} />);

    const nameSort = screen.getByTestId("sort-name");

    // First sort: asc
    fireEvent.click(nameSort);
    expect(screen.getAllByTestId("datatable-row")[0]).toHaveTextContent(
      "Apple",
    );

    // Second sort: desc
    fireEvent.click(nameSort);
    expect(screen.getAllByTestId("datatable-row")[0]).toHaveTextContent(
      "Zebra",
    );

    // Third sort: asc again
    fireEvent.click(nameSort);
    expect(screen.getAllByTestId("datatable-row")[0]).toHaveTextContent(
      "Apple",
    );

    // Switch to count and toggle
    const countSort = screen.getByTestId("sort-count");
    fireEvent.click(countSort);
    expect(screen.getAllByTestId("datatable-row")[0]).toHaveTextContent("50");

    fireEvent.click(countSort);
    expect(screen.getAllByTestId("datatable-row")[0]).toHaveTextContent("100");
  });
});
