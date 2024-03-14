from flask import Flask, render_template, request
import plotly
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from pymongo import MongoClient
import json
from datetime import datetime
from configparser import ConfigParser

app = Flask(__name__)

# Load configuration file
config = ConfigParser()
config.read('config.ini')

# Setup MongoDB Client
#client = MongoClient(config.get('DEAL_API_VALUATION', 'MongoClient'))
client = MongoClient("mongodb://localhost:27017/")
db = client['Deal_Transactions']

def parse_date(date_str):
    """Parse a string date in 'YYYY-MM-DD' format into a datetime object, if provided."""
    return datetime.strptime(date_str, '%Y-%m-%d') if date_str else None

def get_total_valuations(from_date=None, to_date=None, keyword='Bitcoin'):
    match_stage = {"$match": {"Keyword": keyword}}
    if from_date and to_date:
        match_stage["$match"].update({"Date": {"$gte": from_date, "$lte": to_date}})
    
    pipeline = [
        match_stage,
        {
            "$group": {
                "_id": "$Date",
                "TotalRealVolume": {"$sum": "$Volume"},
                "TotalInitVolume": {"$sum": "$Init_Volume"},
                "TotalEffectiveVolume": {"$sum": {"$add": ["$Volume", "$Sold_Volume"]}},
                "TotalExpectedVolume": {"$sum": {"$add": ["$Volume", {"$divide": ["$Sold_Amount", "$Init_Price"]}]}},
                "TotalInitAmount": {"$sum": {"$multiply": ["$Init_Volume", "$Price"]}},
                "TotalEffectiveAmount": {"$sum": {"$add": [{"$multiply": ["$Volume", "$Price"]}, "$Sold_Amount"]}},
                "TotalExpectedAmount": {"$sum": {"$multiply": [{"$add": ["$Volume", {"$divide": ["$Sold_Amount", "$Init_Price"]}]}, "$Price"]}}
            }
        },
        {"$sort": {"_id": 1}}
    ]
    
    result = db["Valuations"].aggregate(pipeline)
    return pd.DataFrame(list(result))

def get_deal_valuations(from_date=None, to_date=None, keyword='Bitcoin'):
    query = {"Keyword": keyword}
    if from_date and to_date:
        query.update({"Date": {"$gte": from_date, "$lte": to_date}})
    
    valuations = list(db["Valuations"].find(query))
    for valuation in valuations:
        valuation['DealExpectedVolume'] = valuation['Volume'] + valuation['Sold_Amount'] / valuation['Init_Price'] if valuation['Init_Price'] else 0 - valuation.get('Init_Volume', 0)
    return pd.DataFrame(valuations)

def get_last_day_valuations(end_date, keyword='Bitcoin'):
    query = {"Keyword": keyword, "Date": end_date}
    valuations = list(db["Valuations"].find(query))
    for valuation in valuations:
        valuation['DealSoldVolume'] = valuation['Volume'] + valuation.get('Sold_Volume', 0)
        valuation['DealExpectedVolume'] = valuation['Volume'] + valuation['Sold_Amount'] / valuation['Init_Price'] if valuation['Init_Price'] else 0
    return pd.DataFrame(valuations)

@app.route('/', methods=['GET', 'POST'])
def index():
    from_date_str = request.args.get('from_date', '2023-01-01')
    to_date_str = request.args.get('to_date', '2024-03-12')
    keyword = request.args.get('keyword', 'Bitcoin') 
    from_date = parse_date(from_date_str)
    to_date = parse_date(to_date_str)

    total_data = get_total_valuations(from_date, to_date, keyword)
    total_data.rename(columns={
        '_id': 'Date',
        'TotalRealVolume': 'Total Real Volume',
        'TotalInitVolume': 'Total Init Volume',
        'TotalEffectiveVolume': 'Total Effective Volume',
        'TotalExpectedVolume': 'Total Expected Volume',
        'TotalInitAmount': 'Total Init Amount',
        'TotalEffectiveAmount': 'Total Effective Amount',
        'TotalExpectedAmount': 'Total Expected Amount'
    }, inplace=True)
	
    deal_data = get_deal_valuations(from_date, to_date, keyword)
    deal_data.rename(columns={
        'DealExpectedVolume': 'Deal Expected Volume'
    }, inplace=True)

    price_data = deal_data[['Date', 'Price']].drop_duplicates().sort_values(by='Date')
    fig1 = px.line(price_data, x='Date', y='Price', title='<b>Daily Fluctuation Price</b><br><i>Day by Day for ' + keyword + '</i>', labels={'Price': 'Price ($)', 'Date': 'Date'})
    graphJSON1 = json.dumps(fig1, cls=plotly.utils.PlotlyJSONEncoder)

    fig2 = px.line(total_data, x='Date', y=['Total Real Volume', 'Total Effective Volume'], title='<b>Total Effective Volume</b><br><i>real volume AND real volume + sold volume</i>', labels={'value':'Effective', 'variable':'Type'})
    graphJSON2 = json.dumps(fig2, cls=plotly.utils.PlotlyJSONEncoder)
    
    fig3 = px.line(total_data, x='Date', y=['Total Init Volume', 'Total Effective Volume', 'Total Expected Volume'], title='<b>Total Expected Volume</b><br><i>init volume AND real volume + sold volume AND real volume + expected volume</i>', labels={'value':'Expected', 'variable':'Type'})
    graphJSON3 = json.dumps(fig3, cls=plotly.utils.PlotlyJSONEncoder)
    
    fig4 = px.line(deal_data, x='Date', y='Deal Expected Volume', color='DealUID', title='<b>Deal Expected Volume</b><br><i>(real volume + expected volume) - initial volume</i>', labels={'value':'Expected', 'DealUID':'Deal UID'})
    graphJSON4 = json.dumps(fig4, cls=plotly.utils.PlotlyJSONEncoder)

    fig5 = px.line(total_data, x='Date', y=['Total Init Amount', 'Total Effective Amount', 'Total Expected Amount'], title='<b>Total Expected Valuation</b><br><i>init volume * price AND real volume * price + sold amount AND (real volume + epected volume) * price</i>', labels={'value':'Expected', 'variable':'Type'})
    graphJSON5 = json.dumps(fig5, cls=plotly.utils.PlotlyJSONEncoder)

    last_day_data = get_last_day_valuations(to_date, keyword)
    last_day_data.sort_values(by='DealUID', inplace=True)
    last_day_data.rename(columns={
        'DealSoldVolume': 'Deal Sold Volume',
        'DealExpectedVolume': 'Deal Expected Volume',
    }, inplace=True)
    
    fig6 = go.Figure()
    fig6.add_trace(go.Bar(x=last_day_data['DealUID'], y=last_day_data['Deal Expected Volume'], name='Expected Volume',
                          marker_color='rgba(153, 102, 255, 0.6)', 
                          ))
    fig6.add_trace(go.Bar(x=last_day_data['DealUID'], y=last_day_data['Deal Sold Volume'], name='Sold Volume',
                          marker_color='rgba(255, 159, 64, 0.6)', 
                          ))
    fig6.add_trace(go.Bar(x=last_day_data['DealUID'], y=last_day_data['Volume'], name='Actual Volume',
                          marker_color='rgba(54, 162, 235, 0.6)',
                          ))
    fig6.update_layout(
        title=f'<b>Deal Last Volume</b><br><i>on {to_date_str}</i>',
        xaxis_title="Deal UID",
        yaxis_title="Volume",
        barmode='overlay'
    )
    graphJSON6 = json.dumps(fig6, cls=plotly.utils.PlotlyJSONEncoder)

    last_day_data['Deal Effective Amount'] = last_day_data['Volume'] * last_day_data['Price']
    last_day_data['Deal Sold Amount'] = last_day_data['Deal Sold Volume'] * last_day_data['Price']
    last_day_data['Deal Expected Amount'] = last_day_data['Deal Expected Volume'] * last_day_data['Price']
    
    fig7 = go.Figure()
    fig7.add_trace(go.Bar(x=last_day_data['DealUID'], y=last_day_data['Deal Expected Amount'], name='Expected Amount',
                          marker_color='rgba(153, 102, 235, 0.7)'))
    fig7.add_trace(go.Bar(x=last_day_data['DealUID'], y=last_day_data['Deal Sold Amount'], name='Sold Amount',
                          marker_color='rgba(255, 206, 86, 0.7)'))
    fig7.add_trace(go.Bar(x=last_day_data['DealUID'], y=last_day_data['Deal Effective Amount'], name='Actual Amount',
                          marker_color='rgba(75, 192, 192, 0.7)'))
    fig7.update_layout(
        title='<b>Deal Last Valuation</b><br><i>on ' + to_date_str + '</i>',
        xaxis_title="Deal UID",
        yaxis_title="Valuation",
        barmode='overlay'
    )
    graphJSON7 = json.dumps(fig7, cls=plotly.utils.PlotlyJSONEncoder)

    return render_template('chart.html', 
                           graphJSON1=graphJSON1, graphJSON2=graphJSON2, 
                           graphJSON3=graphJSON3, graphJSON4=graphJSON4,
                           graphJSON5=graphJSON5, graphJSON6=graphJSON6, 
                           graphJSON7=graphJSON7,
                           from_date=from_date_str, to_date=to_date_str, keyword=keyword)

if __name__ == '__main__':
    app.run(debug=True)