import re
import mysql.connector
import dash
import dash_cytoscape as cyto
from dash import dcc, html, callback_context
from dash.dependencies import Input, Output, State, ALL
import dash.exceptions

# DB 接続設定（環境に合わせて変更してください）
DB_CONFIG = {
    'host': 'localhost',      # 例: 'localhost'
    'user': 'ec_user',        # 例: 'root'
    'password': 'ec_pass',    # 例: 'password'
    'database': 'ec_db'
}

# カラーパレット
PRIMARY_COLOR = "#FF4B3C"
SECONDARY_COLOR = "#FAA500"
ACCENT_COLOR = "#3282C8"    # （必要に応じて使用）

def fetch_schema_data(db_config):
    """MySQL の INFORMATION_SCHEMA からテーブル情報と依存関係を取得する。

    各テーブルの主キーは "id" とし、外部キーは
    "<参照先テーブル名>_id" の形式で定義されていると仮定する。
    """
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor(dictionary=True)
    query = """
        SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, COLUMN_COMMENT
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = %s
        ORDER BY TABLE_NAME, ORDINAL_POSITION
    """
    cursor.execute(query, (db_config['database'],))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    tables = {}
    for row in rows:
        table_name = row['TABLE_NAME']
        if table_name not in tables:
            tables[table_name] = {'columns': []}
        tables[table_name]['columns'].append({
            'name': row['COLUMN_NAME'],
            'type': row['COLUMN_TYPE'],
            'comment': row['COLUMN_COMMENT'] or ''
        })
    dependencies = []
    pattern = re.compile(r'(.+)_id$')
    for table_name, table_info in tables.items():
        for col in table_info['columns']:
            col_name = col['name']
            if col_name == "id":
                continue
            m = pattern.match(col_name)
            if m:
                ref_table = m.group(1)
                if ref_table in tables:
                    dependencies.append((table_name, ref_table))
    return tables, dependencies

def generate_elements(tables, dependencies, filter_text=""):
    """Cytoscape 用の要素リストを生成する。"""
    nodes = {}
    for table_name in tables:
        if filter_text.lower() in table_name.lower():
            nodes[table_name] = {
                'data': {
                    'id': table_name,
                    'label': table_name,
                    'details': tables[table_name]
                }
            }
    edges = []
    for src, tgt in dependencies:
        if src in nodes and tgt in nodes:
            edges.append({
                'data': {
                    'source': src,
                    'target': tgt
                }
            })
    return list(nodes.values()) + edges

def format_table_details(table_name, table_info):
    """テーブルの詳細情報を読みやすいテキスト形式に整形する。"""
    header = table_name
    separator = "-" * len(header)
    lines = [header, separator]
    for col in table_info.get('columns', []):
        line = f"- {col['name']}: {col['type']}"
        if col['comment']:
            line = f"{line} {col['comment']}"
        lines.append(line)
    return "\n".join(lines)

def create_app():
    global tables, dependencies
    tables, dependencies = fetch_schema_data(DB_CONFIG)
    app = dash.Dash(__name__)
    server = app.server

    base_stylesheet = [
        {'selector': 'node',
         'style': {'label': 'data(label)', 'background-color': '#CCCCCC'}},
        {'selector': 'edge',
         'style': {'line-color': '#CCCCCC', 'line-opacity': '0.8'}}
    ]

    app.layout = html.Div(
        style={'display': 'flex', 'height': '100vh',
               'fontFamily': '"Noto Sans", sans-serif'},
        children=[
            html.Link(
                href="https://fonts.googleapis.com/css2?family=Noto+Sans:wght@400;700&display=swap",
                rel="stylesheet"
            ),
            # 左サイドバー: テーブルフィルター＆一覧
            html.Div(
                id='left-sidebar',
                style={
                    'width': '20%',
                    'maxWidth': '300px',
                    'borderRight': '1px solid #ccc',
                    'padding': '10px',
                    'overflowY': 'auto'
                },
                children=[
                    html.H3(f"{len(tables)} Tables"),
                    dcc.Input(
                        id="filter-input",
                        type="text",
                        placeholder="Filter tables",
                        style={'width': '90%', 'marginBottom': '10px', 'height': '1.5rem'}
                    ),
                    html.Div(id='table-list')
                ]
            ),
            # 中央: Cytoscape グラフエリア
            html.Div(
                id='center-graph',
                style={
                    'flex': '1',
                    'padding': '10px',
                    'position': 'relative',
                    'display': 'flex',
                    'flexDirection': 'column'
                },
                children=[
                    cyto.Cytoscape(
                        id='cytoscape',
                        elements=generate_elements(tables, dependencies),
                        layout={'name': 'concentric'},
                        stylesheet=base_stylesheet,
                        style={'flex': '1', 'width': '100%'}
                    ),
                    html.Div(
                        style={
                            'marginTop': '10px',
                            'position': 'absolute',
                            'top': '1rem',
                            'left': '1rem',
                            'display': 'flex',
                            'alignItems': 'center'
                        },
                        children=[
                            html.Label("Layout:", style={'marginRight': '0.5rem'}),
                            dcc.Dropdown(
                                id='layout-dropdown',
                                options=[
                                    {'label': 'Concentric', 'value': 'concentric'},
                                    {'label': 'Circle', 'value': 'circle'},
                                    {'label': 'COSE', 'value': 'cose'},
                                    {'label': 'Breadthfirst', 'value': 'breadthfirst'},
                                    {'label': 'Grid', 'value': 'grid'},
                                ],
                                value='concentric',
                                clearable=False,
                                style={'width': '200px',
                                       'display': 'inline-block'}
                            )
                        ]
                    )
                ]
            ),
            # 右サイドバー: テーブル詳細＆関連テーブル
            html.Div(
                id='right-sidebar',
                style={
                    'width': '20%',
                    'borderLeft': '1px solid #ccc',
                    'padding': '10px',
                    'overflowY': 'auto'
                },
                children=[
                    html.H3("Table Details"),
                    html.Pre(
                        id='table-details',
                        style={
                            'whiteSpace': 'pre-wrap',
                            'border': '1px solid #ccc',
                            'padding': '10px'
                        }
                    ),
                    html.H3("Related Tables", style={'marginTop': '2rem'}),
                    html.Pre(
                        id='related-tables',
                        style={
                            'whiteSpace': 'pre-wrap',
                            'border': '1px solid #ccc',
                            'padding': '10px'
                        }
                    )
                ]
            ),
            # Store for selected table
            dcc.Store(id='selected-table-store')
        ]
    )

    @app.callback(
        Output('cytoscape', 'elements'),
        Input('filter-input', 'value')
    )
    def update_elements(filter_text):
        filter_text = filter_text or ""
        return generate_elements(tables, dependencies, filter_text)

    @app.callback(
        Output('table-list', 'children'),
        [Input('filter-input', 'value'),
         Input('selected-table-store', 'data')]
    )
    def update_table_list(filter_text, selected_store):
        filter_text = filter_text or ""
        filtered_tables = sorted(
            [t for t in tables if filter_text.lower() in t.lower()]
        )
        selected_value = (selected_store['selected']
                          if (selected_store and 'selected' in selected_store)
                          else None)
        # Compute neighbors if a table is selected
        neighbors = set()
        if selected_value:
            for src, tgt in dependencies:
                if src == selected_value:
                    neighbors.add(tgt)
                elif tgt == selected_value:
                    neighbors.add(src)
        table_buttons = []
        for tname in filtered_tables:
            style = {
                'width': '100%',
                'textAlign': 'left',
                'marginBottom': '5px',
                'overflowWrap': 'break-word'
            }
            if tname == selected_value:
                style.update({'background-color': PRIMARY_COLOR, 'color': 'white'})
            elif tname in neighbors:
                style.update({'background-color': SECONDARY_COLOR, 'color': 'white'})
            table_buttons.append(
                html.Button(
                    tname,
                    id={'type': 'table-item', 'index': tname},
                    n_clicks=0,
                    style=style
                )
            )
        return table_buttons

    @app.callback(
        Output('selected-table-store', 'data'),
        [Input({'type': 'table-item', 'index': ALL}, 'n_clicks'),
         Input('cytoscape', 'tapNodeData')],
        [State({'type': 'table-item', 'index': ALL}, 'id'),
         State('selected-table-store', 'data')]
    )
    def update_selected(left_clicks, tap_data, left_ids, current_store):
        ctx = callback_context
        if not ctx.triggered:
            raise dash.exceptions.PreventUpdate
        trigger = ctx.triggered[0]['prop_id']
        new_selected = None
        if 'tapNodeData' in trigger and tap_data:
            new_selected = tap_data.get('id')
        else:
            for n, comp_id in zip(left_clicks, left_ids):
                if n and n > 0:
                    new_selected = comp_id['index']
                    break
        if new_selected is None:
            return current_store
        if current_store and current_store.get('selected') == new_selected:
            return dash.no_update
        return {'selected': new_selected}

    @app.callback(
        Output('cytoscape', 'stylesheet'),
        Input('selected-table-store', 'data')
    )
    def update_stylesheet(selected_store):
        base = [
            {'selector': 'node',
             'style': {'label': 'data(label)', 'background-color': '#CCCCCC'}},
            {'selector': 'edge',
             'style': {'line-color': '#CCCCCC', 'line-opacity': '0.8'}}
        ]
        if not selected_store or 'selected' not in selected_store:
            return base
        selected = selected_store['selected']
        neighbors = set()
        for src, tgt in dependencies:
            if src == selected:
                neighbors.add(tgt)
            elif tgt == selected:
                neighbors.add(src)
        highlight = [
            {'selector': f'node[id="{selected}"]',
             'style': {'background-color': PRIMARY_COLOR}},
            {'selector': f'edge[source="{selected}"], edge[target="{selected}"]',
             'style': {'line-color': PRIMARY_COLOR, 'line-opacity': '0.8'}}
        ]
        if neighbors:
            neighbor_selector = ", ".join(
                [f'node[id="{n}"]' for n in neighbors]
            )
            highlight.append(
                {'selector': neighbor_selector,
                 'style': {'background-color': SECONDARY_COLOR}}
            )
        return base + highlight

    @app.callback(
        [Output('table-details', 'children'),
         Output('related-tables', 'children')],
        Input('selected-table-store', 'data')
    )
    def display_details(selected_store):
        if not selected_store or 'selected' not in selected_store:
            return "Click on a node to see details.", ""
        selected = selected_store['selected']
        main_details = format_table_details(selected, tables.get(selected, {}))
        related = set()
        for src, tgt in dependencies:
            if src == selected:
                related.add(tgt)
            elif tgt == selected:
                related.add(src)
        if related:
            related_details = "\n\n".join(
                [format_table_details(rt, tables.get(rt, {}))
                 for rt in sorted(related)]
            )
        else:
            related_details = "No related tables."
        return main_details, related_details

    @app.callback(
        Output('cytoscape', 'layout'),
        Input('layout-dropdown', 'value')
    )
    def update_layout(layout_value):
        return {'name': layout_value}

    return app

if __name__ == '__main__':
    app = create_app()
    app.title = "ER視る"
    # app.run_server(debug=True, port=8887)
    app.run_server(debug=False, port=3005)

