from flask import Flask, render_template, request, redirect, url_for, session, send_file
import pandas as pd
import plotly.graph_objects as go
import os
import dash
from dash import dcc, html
import dash_table
from dash.dependencies import Input, Output, State
import io
import uuid
import tempfile

# Flask app setup
app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Temporary folder for storing uploaded files
TEMP_FOLDER = tempfile.gettempdir()

# Dash app setup (Separate Dash app from Flask app)
dash_app = dash.Dash(__name__, server=app, routes_pathname_prefix="/dash/", suppress_callback_exceptions=True)

# Dash app layout
dash_app.layout = html.Div([
    dcc.Store(id='page-index', data=0),
    dcc.Store(id='total-pages', data=1),
    dcc.Store(id='file-id', data=None),  # Store for the file identifier
    
    # Content that will be shown or hidden based on file upload
    html.Div(id='table-container', children=[
        html.H3('Data Table'),
        html.Div([
            html.Button('Previous', id='prev-btn', n_clicks=0, style={'margin-right': '10px'}),
            html.Div(id='page-indicator', children='Page 1/1', style={
                'display': 'inline-block',
                'padding': '5px 15px',
                'margin': '0 10px'
            }),
            html.Button('Next', id='next-btn', n_clicks=0, style={'margin-left': '10px'})
        ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'center', 'margin': '10px 0'}),
        dash_table.DataTable(id='data-table', persistence=False, data=[], page_size=20)
    ], style={'display': 'none'})  # Initially hidden
])

# Function to check if the file extension is allowed
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() == 'xlsx'

# Smoothing function
def smooth_data(y_values, window_size=10):
    return pd.Series(y_values).rolling(window=window_size, min_periods=1).mean()

# Function to process the Excel file data
def process_excel_data(file_path):
    # Read the Excel file
    df = pd.read_excel(file_path, engine='openpyxl')
    
    # Rename columns based on the first row
    df.columns = ["T_1K", "CTE_1K", "T_3K", "CTE_3K", "T_6K", "CTE_6K", "T_10K", "CTE_10K"]
    
    # Drop the first row if it contains headers
    df = df.iloc[1:].reset_index(drop=True)
    
    # Convert all data to numeric values and drop rows with missing values
    df = df.apply(pd.to_numeric, errors='coerce')
    df.dropna(inplace=True)
    
    return df

# Home route for rendering static index page
@app.route('/')
def index():
    return render_template('index.html')

# About page (static content)
@app.route('/about')
def about():
    return render_template('about.html')

# Contact page (static content)
@app.route('/contact')
def contact():
    return render_template('contact.html')

# Dashboard page for file upload and visualization
@app.route('/app', methods=['GET', 'POST'])
def dashboard():
    # Clear old graphs if it's a GET request
    if request.method == 'GET':
        # Only clear if user is explicitly loading the page (not via redirect)
        if request.args.get('keep_data') != '1':
            session.pop('file_id', None)
    
    graphs_html = []  # Initialize a list to hold all graph HTMLs
    
    # Get file_id from session if exists
    file_id = session.get('file_id')
    
    # If no file_id in session but should be (after POST), handle file upload
    if request.method == 'POST':
        # Check if the post request has the file part
        file = request.files.get('file')
        
        if file and allowed_file(file.filename):
            # Generate a unique ID for this file
            file_id = str(uuid.uuid4())
            
            # Save file to temporary location
            file_path = os.path.join(TEMP_FOLDER, f"{file_id}.xlsx")
            file.save(file_path)
            
            # Store file_id in session
            session['file_id'] = file_id
    
    # If we have a file_id, process and display the data
    if file_id:
        file_path = os.path.join(TEMP_FOLDER, f"{file_id}.xlsx")
        
        if os.path.exists(file_path):
            # Process the Excel data
            df = process_excel_data(file_path)
            
            # Create individual figures for each rate
            rates = [
                {"title": "1K/min", "T": "T_1K", "CTE": "CTE_1K"},
                {"title": "3K/min", "T": "T_3K", "CTE": "CTE_3K"},
                {"title": "6K/min", "T": "T_6K", "CTE": "CTE_6K"},
                {"title": "10K/min", "T": "T_10K", "CTE": "CTE_10K"}
            ]
            
            for rate in rates:
                fig = go.Figure()
                
                # Add raw data
                fig.add_trace(go.Scatter(
                    x=df[rate["T"]], 
                    y=df[rate["CTE"]], 
                    mode='lines', 
                    name=f"{rate['title']} (Original)", 
                    line=dict(color='#FF5252', width=1)  # Changed from red to a nicer red
                ))
                
                # Add smoothed data
                fig.add_trace(go.Scatter(
                    x=df[rate["T"]], 
                    y=smooth_data(df[rate["CTE"]]), 
                    mode='lines', 
                    name=f"{rate['title']} (Smoothed)", 
                    line=dict(color='#4285F4', width=2)  # Changed from cyan to blue
                ))
                
                # Update layout
                fig.update_layout(
                    title_text=f"CTE vs Temperature at {rate['title']} (Original & Smoothed Overlay)",
                    template="plotly_white",  # Changed from plotly_dark to plotly_white
                    height=500,
                    width=900,
                    xaxis_title="Temperature",
                    yaxis_title="CTE"
                )
                
                # Convert Plotly figure to HTML iframe and add to list
                graphs_html.append(fig.to_html(full_html=False, include_plotlyjs='cdn'))
    
    return render_template('app.html', graphs_html=graphs_html, dash_content=dash_app.index())

# Route for downloading the processed file
@app.route('/download')
def download_file():
    file_id = session.get('file_id')
    
    if file_id:
        file_path = os.path.join(TEMP_FOLDER, f"{file_id}.xlsx")
        
        if os.path.exists(file_path):
            try:
                # Get window size from query parameters, default to 10
                window_size = int(request.args.get('window_size', 10))
                
                # Process the Excel data
                df = process_excel_data(file_path)
                
                # Apply smoothing with the selected window size
                for col in df.columns[1::2]:
                    df[col + '_Smoothed'] = smooth_data(df[col], window_size=window_size)
                
                # Save to an in-memory file
                output = io.BytesIO()
                df.to_excel(output, engine='openpyxl', index=False)
                output.seek(0)
                
                return send_file(output, download_name='smoothed_data.xlsx', as_attachment=True)
            except Exception as e:
                print(f"Error processing file: {e}")
    
    return redirect(url_for('dashboard'))

# Dash callback to update the table based on uploaded file in session
@dash_app.callback(
    Output('data-table', 'data'),
    Output('prev-btn', 'disabled'),
    Output('next-btn', 'disabled'),
    Output('page-index', 'data'),
    Output('page-indicator', 'children'),
    Output('total-pages', 'data'),
    Output('table-container', 'style'),  # Add output for table container style
    Input('prev-btn', 'n_clicks'),
    Input('next-btn', 'n_clicks'),
    State('page-index', 'data'),
    State('total-pages', 'data'),
    State('file-id', 'data')
)
def update_table(prev_clicks, next_clicks, current_page, stored_total_pages, dash_file_id):
    # Try to get file_id from Dash store, fallback to session if not available
    file_id = dash_file_id or session.get('file_id')
    
    if file_id:
        file_path = os.path.join(TEMP_FOLDER, f"{file_id}.xlsx")
        
        if os.path.exists(file_path):
            # Process the Excel data
            df = process_excel_data(file_path)
            
            # Paginate the DataFrame (show 20 rows per page)
            page_size = 20
            total_pages = max((len(df) + page_size - 1) // page_size, 1)
            
            # Identify which button was clicked
            triggered_id = dash.ctx.triggered_id if hasattr(dash, 'ctx') else None
            
            # Adjust page index based on button clicks
            if triggered_id == 'prev-btn':
                current_page = max(current_page - 1, 0)
            elif triggered_id == 'next-btn':
                current_page = min(current_page + 1, total_pages - 1)
            
            # Return the current page of data
            start_row = current_page * page_size
            end_row = start_row + page_size
            df_page = df.iloc[start_row:end_row]
            
            # Disable buttons at the boundaries
            prev_disabled = current_page == 0
            next_disabled = current_page >= total_pages - 1
            
            # Update page indicator text
            page_indicator_text = f"Page {current_page + 1}/{total_pages}"
            
            # Show the table container
            table_style = {'display': 'block'}
            
            return df_page.to_dict('records'), prev_disabled, next_disabled, current_page, page_indicator_text, total_pages, table_style
    
    # Hide the table container if no file
    table_style = {'display': 'none'}
    return [], True, True, 0, "Page 1/1", 1, table_style

# Dash callback to synchronize file_id between Flask session and Dash
@dash_app.callback(
    Output('file-id', 'data'),
    Input('table-container', 'children')  # Dummy input to trigger the callback on page load
)
def sync_file_id(_):
    return session.get('file_id')

if __name__ == '__main__':
    app.run(debug=True)