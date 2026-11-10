# OpsFlow Power BI report

Download the Power BI data pack from the Operations dashboard and extract the ZIP to a local folder. It contains CSV snapshots from the same authenticated operations database.

In Power BI Desktop, use Get data > Text/CSV to load `orders.csv`, `order_items.csv`, `clients.csv`, `products.csv`, `shipments.csv`, and `data_issues.csv`. Promote the first row to headers and set IDs and quantities to whole numbers. Set order and shipment dates to Date. Treat tracking numbers, SKU, and phone as Text.

Create these relationships with single-direction filtering from the one side to the many side.

| One side | Many side |
| --- | --- |
| clients[id] | orders[client_id] |
| orders[id] | order_items[order_id] |
| products[id] | order_items[product_id] |
| orders[id] | shipments[order_id] |

Copy the measures in `measures.dax` into the orders and shipments tables using New measure. Add cards for total, pending, completed, delayed shipments, and on-time percentage. Add a column chart of orders by order_date month, a bar chart of order counts by client name, and slicers for order status and direction. Add a quality table using data_issues filtered to status `open`.

Save the resulting report as `OpsFlow.pbix`. When records change, export a new data pack, replace the CSVs in the same folder, and refresh Power BI. These exports are snapshots. The dashboard inside OpsFlow reads the database whenever it is refreshed.

An apostrophe is added to text beginning with spreadsheet formula characters to preserve it as text in spreadsheet imports.

The project includes the data model and measures for Power BI. A native PBIX file must be created and saved using Power BI Desktop.

Microsoft's connector instructions are available at [Text/CSV connector](https://learn.microsoft.com/en-us/power-query/connectors/text-csv).
