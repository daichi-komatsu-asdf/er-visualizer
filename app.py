import re
import mysql.connector
import dash
import dash_cytoscape as cyto
from dash import dcc, html
from dash.dependencies import Input, Output, State, ALL
import dash.exceptions

# =======================================
# DB 接続設定（環境に合わせて変更してください）
# =======================================
DB_CONFIG = {
    'host': 'localhost',  # 例: 'localhost'
    'user': 'ec_user',  # 例: 'root'
    'password': 'ec_pass',   # 例: 'password'
    'database': 'ec_db'
}

# =======================================
# スキーマ情報取得と依存関係抽出の関数群
# =======================================
def fetch_schema_data(db_config):
    """
    MySQL の INFORMATION_SCHEMA から対象データベースの
    テーブル名、カラム名、型、コメントを取得し、
    各テーブルのカラム情報と、外部キーとみなせる依存関係を抽出する。

    前提:
      - 各テーブルの主キーは「id」
      - 外部キーは「<参照先テーブル名>_id」という命名規則で定義されている
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

    # 各テーブル毎にカラム情報をまとめる
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

    # 依存関係抽出
    # 「id」以外のカラムで、名前が "<参照先>_id" にマッチするものを外部キーとみなす
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
    """
    テーブル情報と依存関係から Cytoscape 用の要素リストを生成する。
    filter_text に一致するテーブルのみを対象とし、
    エッジは両端がフィルタ対象のテーブルの場合のみ追加する。
    """
    nodes = {}
    for table_name in tables.keys():
        if filter_text.lower() in table_name.lower():
            nodes[table_name] = {
                'data': {
                    'id': table_name,
                    'label': table_name,
                    # 詳細情報は後のコールバックで利用
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
    """
    指定されたテーブルの詳細情報（テーブル名、各カラムの名前・型・コメント）を
    読みやすいテキスト形式に整形する。
    """
    header = table_name
    separator = "-" * len(header)
    lines = [header, separator]
    for col in table_info.get('columns', []):
        line = f"- {col['name']}: {col['type']}"
        if col['comment'] != '':
            line = f"{line} {col['comment']}"
        lines.append(line)
    return "\n".join(lines)

# =======================================
# Dash アプリ生成（create_app 関数内にまとめる）
# =======================================
def create_app():
    # DB からスキーマ情報と依存関係を取得
    tables, dependencies = fetch_schema_data(DB_CONFIG)

    app = dash.Dash(__name__)
    server = app.server  # デプロイ用にも利用可能

    app.layout = html.Div(style={'display': 'flex', 'height': '100vh'}, children=[
        # 左側サイドバー（幅20%程度）
        html.Div(id='left-sidebar', style={
            'width': '20%', 'maxWidth': '300px', 'borderRight': '1px solid #ccc', 'padding': '10px', 'overflowY': 'auto'
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
        # 中央：グラフ表示エリア
        html.Div(id='center-graph', style={
            'flex': '1', 'padding': '10px', 'position': 'relative', 'display': 'flex', 'flexDirection': 'column'
        }, children=[
            cyto.Cytoscape(
                id='cytoscape',
                elements=generate_elements(tables, dependencies),
                layout={'name': 'cose'},
                stylesheet=[
                    {
                        'selector': 'node',
                        'style': {
                            'label': 'data(label)',
                            'background-color': '#CCCCCC'
                        }
                    },
                    {
                        'selector': 'edge',
                        'style': {
                            'line-color': '#DDDDDD'
                        }
                    },
                    {
                        'selector': '.selected',
                        'style': {
                            'background-color': '#F39C12',
                            'line-color': '#F39C12'
                        }
                    },
                    {
                        'selector': '.adjacent',
                        'style': {
                            'background-color': '#F7DC6F',
                            'line-color': '#F7DC6F'
                        }
                    }
                ],
                style={'flex': '1', 'width': '100%'}
            ),
            html.Div(style={'marginTop': '10px', 'position': 'absolute', 'top': '1rem', 'left': '1rem', 'display': 'flex', 'align-items': 'center'}, children=[
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
                    style={'width': '200px', 'display': 'inline-block' }
                )
            ])
        ]),
        # 右側：テーブル詳細＆関連テーブル表示エリア（幅20%程度）
        html.Div(id='right-sidebar', style={
            'width': '20%', 'borderLeft': '1px solid #ccc', 'padding': '10px', 'overflowY': 'auto'
        }, children=[
            html.H3("Table Details"),
            html.Pre(id='table-details', style={'whiteSpace': 'pre-wrap', 'border': '1px solid #ccc', 'padding': '10px'}),
            html.H3("Related Tables", style={'marginTop': '2rem'}),
            html.Pre(id='related-tables', style={'whiteSpace': 'pre-wrap', 'border': '1px solid #ccc', 'padding': '10px'})
        ]),
        # 選択されたテーブル名を保持する dcc.Store とクライアントサイドコールバック用のダミー Div
        dcc.Store(id='selected-table-store'),
        html.Div(id='dummy-div', style={'display': 'none'})
    ])

    # ------------------------------------------------
    # ① フィルター入力に応じてグラフの要素と左側テーブル一覧を更新
    # ------------------------------------------------
    @app.callback(
        [Output('cytoscape', 'elements'),
         Output('table-list', 'children')],
        Input('filter-input', 'value')
    )
    def update_elements_and_table_list(filter_text):
        if not filter_text:
            filter_text = ""
        elements = generate_elements(tables, dependencies, filter_text)
        filtered_tables = sorted([t for t in tables.keys() if filter_text.lower() in t.lower()])
        table_buttons = []
        for tname in filtered_tables:
            table_buttons.append(
                html.Button(
                    tname,
                    id={'type': 'table-item', 'index': tname},
                    n_clicks=0,
                    style={'width': '100%', 'textAlign': 'left', 'marginBottom': '5px', 'overflowWrap': 'break-word'}
                )
            )
        return elements, table_buttons

    # ------------------------------------------------
    # ② 左側のテーブルボタンがクリックされたとき、そのテーブル名を dcc.Store に保持
    # ------------------------------------------------
    @app.callback(
        Output('selected-table-store', 'data'),
        Input({'type': 'table-item', 'index': ALL}, 'n_clicks'),
        State({'type': 'table-item', 'index': ALL}, 'id')
    )
    def update_selected_table(n_clicks_list, ids):
        ctx = dash.callback_context
        if not ctx.triggered:
            raise dash.exceptions.PreventUpdate
        for n, comp_id in zip(n_clicks_list, ids):
            if n and n > 0:
                return comp_id['index']
        return dash.no_update

    # ------------------------------------------------
    # ③ クライアントサイドコールバックで、選択されたテーブルのノードをグラフ中央に移動し、
    #     隣接ノードおよびエッジにハイライト（selected, adjacent クラス付与）を行う
    # ------------------------------------------------
    app.clientside_callback(
        """
        function(selectedTable) {
            if (!selectedTable) {
                return "";
            }
            var cyElem = document.getElementById('cytoscape');
            if (cyElem && cyElem.cy) {
                var cy = cyElem.cy;
                // すべてのノードとエッジからクラスをクリア
                cy.elements().removeClass('selected');
                cy.elements().removeClass('adjacent');
                var node = cy.getElementById(selectedTable);
                if (node) {
                    node.addClass('selected');
                    var connectedEdges = node.connectedEdges();
                    connectedEdges.addClass('adjacent');
                    var connectedNodes = node.neighborhood('node');
                    connectedNodes.addClass('adjacent');
                    cy.center(node);
                }
            }
            return "";
        }
        """,
        Output('dummy-div', 'children'),
        Input('selected-table-store', 'data')
    )

    # ------------------------------------------------
    # ④ レイアウト切替（ドロップダウン）
    # ------------------------------------------------
    @app.callback(
        Output('cytoscape', 'layout'),
        Input('layout-dropdown', 'value')
    )
    def update_layout(layout_value):
        return {'name': layout_value}

    # ------------------------------------------------
    # ⑤ ノードタップで右側にテーブル詳細と関連テーブルを表示
    # ------------------------------------------------
    @app.callback(
        [Output('table-details', 'children'),
         Output('related-tables', 'children')],
        Input('cytoscape', 'tapNodeData')
    )
    def display_table_details(node_data):
        if node_data is None:
            return "Click on a node to see details.", ""
        table_name = node_data.get('id')
        main_details = format_table_details(table_name, tables.get(table_name, {}))
        related = set()
        for src, tgt in dependencies:
            if src == table_name:
                related.add(tgt)
            elif tgt == table_name:
                related.add(src)
        if related:
            related_details = "\n\n".join(
                [format_table_details(rt, tables.get(rt, {})) for rt in sorted(related)]
            )
        else:
            related_details = "No related tables."
        return main_details, related_details


    return app

# =======================================
# エントリポイント
# =======================================
if __name__ == '__main__':
    app = create_app()
    # app.run_server(debug=False, port=8888)
    app.run_server(debug=True, port=8887)
