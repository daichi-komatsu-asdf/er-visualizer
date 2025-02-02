import re
import mysql.connector
import dash
import dash_cytoscape as cyto
from dash import dcc, html, callback_context
from dash.dependencies import Input, Output, State, ALL
import dash.exceptions

# =======================================
# DB 接続設定（環境に合わせて変更してください）
# =======================================
DB_CONFIG = {
    'host': 'localhost',      # 例: 'localhost'
    'user': 'ec_user',        # 例: 'root'
    'password': 'ec_pass',    # 例: 'password'
    'database': 'ec_db'
}

# =======================================
# スキーマ情報取得と依存関係抽出の関数群
# =======================================
def fetch_schema_data(db_config):
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
    header = table_name
    separator = "-" * len(header)
    lines = [header, separator]
    for col in table_info.get('columns', []):
        line = f"- {col['name']}: {col['type']}"
        if col['comment']:
            line = f"{line} {col['comment']}"
        lines.append(line)
    return "\n".join(lines)

# =======================================
# Dash アプリ生成
# =======================================
def create_app():
    global tables, dependencies
    tables, dependencies = fetch_schema_data(DB_CONFIG)
    app = dash.Dash(__name__)
    server = app.server

    base_stylesheet = [
        {'selector': 'node', 'style': {'label': 'data(label)', 'background-color': '#CCCCCC'}},
        {'selector': 'edge', 'style': {'line-color': '#DDDDDD'}}
    ]

    app.layout = html.Div(style={'display': 'flex', 'height': '100vh'}, children=[
        # 左サイドバー：テーブルフィルター＆一覧
        html.Div(id='left-sidebar', style={
            'width': '20%', 'maxWidth': '300px', 'borderRight': '1px solid #ccc',
            'padding': '10px', 'overflowY': 'auto'
        }, children=[
            html.H3("Tables"),
            dcc.Input(
                id="filter-input",
                type="text",
                placeholder="Filter tables",
                style={'width': '90%', 'marginBottom': '10px'}
            ),
            html.Div(id='table-list')
        ]),
        # 中央：Cytoscape グラフエリア
        html.Div(id='center-graph', style={
            'flex': '1', 'padding': '10px', 'position': 'relative',
            'display': 'flex', 'flexDirection': 'column'
        }, children=[
            cyto.Cytoscape(
                id='cytoscape',
                elements=generate_elements(tables, dependencies),
                layout={'name': 'cose'},
                stylesheet=base_stylesheet,
                style={'flex': '1', 'width': '100%'}
            ),
            html.Div(style={'marginTop': '10px', 'position': 'absolute', 'top': '1rem', 'left': '1rem',
                            'display': 'flex', 'alignItems': 'center'}, children=[
                html.Label("Layout:", style={'marginRight': '0.5rem'}),
                dcc.Dropdown(
                    id='layout-dropdown',
                    options=[
                        {'label': 'COSE', 'value': 'cose'},
                        {'label': 'Breadthfirst', 'value': 'breadthfirst'},
                        {'label': 'Circle', 'value': 'circle'},
                        {'label': 'Grid', 'value': 'grid'},
                    ],
                    value='cose',
                    clearable=False,
                    style={'width': '200px', 'display': 'inline-block'}
                )
            ])
        ]),
        # 右サイドバー：テーブル詳細 & 関連テーブル
        html.Div(id='right-sidebar', style={
            'width': '20%', 'borderLeft': '1px solid #ccc', 'padding': '10px',
            'overflowY': 'auto'
        }, children=[
            html.H3("Table Details"),
            html.Pre(id='table-details', style={'whiteSpace': 'pre-wrap',
                                                  'border': '1px solid #ccc',
                                                  'padding': '10px'}),
            html.H3("Related Tables", style={'marginTop': '2rem'}),
            html.Pre(id='related-tables', style={'whiteSpace': 'pre-wrap',
                                                  'border': '1px solid #ccc',
                                                  'padding': '10px'})
        ]),
        # 選択されたテーブルを保持する Store
        dcc.Store(id='selected-table-store')
    ])

    # ① フィルター入力と Store → グラフ要素 & テーブル一覧更新
    @app.callback(
        [Output('cytoscape', 'elements'),
         Output('table-list', 'children')],
        [Input('filter-input', 'value'),
         Input('selected-table-store', 'data')]
    )
    def update_elements_and_table_list(filter_text, selected_store):
        filter_text = filter_text or ""
        filtered_tables = sorted([t for t in tables if filter_text.lower() in t.lower()])
        table_buttons = []
        selected_value = None
        if selected_store and 'selected' in selected_store:
            selected_value = selected_store['selected']
        for tname in filtered_tables:
            style = {'width': '100%', 'textAlign': 'left',
                     'marginBottom': '5px', 'overflowWrap': 'break-word'}
            if tname == selected_value:
                style.update({'background-color': '#F39C12', 'color': 'white'})
            table_buttons.append(
                html.Button(
                    tname,
                    id={'type': 'table-item', 'index': tname},
                    n_clicks=0,
                    style=style
                )
            )
        triggered_ids = [t['prop_id'] for t in callback_context.triggered]
        if any('selected-table-store' in t for t in triggered_ids) and not any('filter-input' in t for t in triggered_ids):
            return dash.no_update, table_buttons
        elements = generate_elements(tables, dependencies, filter_text)
        return elements, table_buttons

    # ② 左サイドバーのテーブルボタンまたは Cytoscape ノードタップ → Store 更新
    @app.callback(
        Output('selected-table-store', 'data'),
        [Input({'type': 'table-item', 'index': ALL}, 'n_clicks'),
         Input('cytoscape', 'tapNodeData')],
        [State({'type': 'table-item', 'index': ALL}, 'id'),
         State('selected-table-store', 'data')]
    )
    def update_selected_table(left_clicks, tap_data, left_ids, current_store):
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

    # ③ Store の値に応じて Cytoscape の stylesheet（ハイライト）を更新
    @app.callback(
        Output('cytoscape', 'stylesheet'),
        Input('selected-table-store', 'data')
    )
    def update_stylesheet(selected_store):
        base = [
            {'selector': 'node', 'style': {'label': 'data(label)', 'background-color': '#CCCCCC'}},
            {'selector': 'edge', 'style': {'line-color': '#DDDDDD'}}
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
            {'selector': f'node[id="{selected}"]', 'style': {'background-color': '#F39C12'}},
            {'selector': f'edge[source="{selected}"], edge[target="{selected}"]', 'style': {'line-color': '#F39C12'}}
        ]
        if neighbors:
            neighbor_selector = ", ".join([f'node[id="{n}"]' for n in neighbors])
            highlight.append({'selector': neighbor_selector, 'style': {'background-color': '#F7DC6F'}})
        return base + highlight

    # ④ Store の値に応じて右サイドバーに詳細を表示
    @app.callback(
        [Output('table-details', 'children'),
         Output('related-tables', 'children')],
        Input('selected-table-store', 'data')
    )
    def display_table_details(selected_store):
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
                [format_table_details(rt, tables.get(rt, {})) for rt in sorted(related)]
            )
        else:
            related_details = "No related tables."
        return main_details, related_details

    # ⑤ レイアウト切替：ドロップダウンの値に応じて更新
    @app.callback(
        Output('cytoscape', 'layout'),
        Input('layout-dropdown', 'value')
    )
    def update_layout(layout_value):
        return {'name': layout_value}

    return app

if __name__ == '__main__':
    app = create_app()
    app.run_server(debug=True, port=8887)
