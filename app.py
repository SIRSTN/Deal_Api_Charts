from flask import Flask, render_template, request
import plotly
import plotly.express as px
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
                "TotalExpectedVolume": {"$sum": {"$add": ["$Volume", {"$multiply": ["$Sold_Volume", 1.05]}]}},
                "TotalInitAmount": {"$sum": {"$multiply": ["$Init_Volume", "$Price"]}},
                "TotalExpectedAmount": {"$sum": {"$multiply": [{"$add": ["$Volume", {"$multiply": ["$Sold_Volume", 1.05]}]}, "$Price"]}}
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
        valuation['Sold_Volume'] = float(valuation.get('Sold_Volume', 0)) * 1.05
        valuation['DealExpectedVolume'] = valuation['Volume'] + valuation['Sold_Volume'] - valuation.get('Init_Volume', 0)
    return pd.DataFrame(valuations)

@app.route('/', methods=['GET', 'POST'])
def index():
    from_date_str = request.args.get('from_date', '2023-01-01')
    to_date_str = request.args.get('to_date', '2023-12-31')
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
        'TotalExpectedAmount': 'Total Expected Amount'
    }, inplace=True)
	
    deal_data = get_deal_valuations(from_date, to_date, keyword)
    deal_data.rename(columns={
        'DealExpectedVolume': 'Deal Expected Volume'
    }, inplace=True)

    # Adjustments for Plotly Express line plots
    fig1 = px.line(total_data, x='Date', y=['Total Real Volume', 'Total Effective Volume'], title='<b>Total Effective Volume</b><br><i>real volume AND real volume + sold volume</i>', labels={'value':'Effective', 'variable':'Type'})
    graphJSON1 = json.dumps(fig1, cls=plotly.utils.PlotlyJSONEncoder)
    
    fig2 = px.line(total_data, x='Date', y=['Total Init Volume', 'Total Expected Volume'], title='<b>Total Expected Volume</b><br><i>initial volume AND real volume + expected volume</i>', labels={'value':'Expected', 'variable':'Type'})
    graphJSON2 = json.dumps(fig2, cls=plotly.utils.PlotlyJSONEncoder)
    
    fig3 = px.line(deal_data, x='Date', y='Deal Expected Volume', color='DealUID', title='<b>Deal Expected Volume</b><br><i>(real volume + expected volume) - initial volume</i>', labels={'value':'Expected', 'DealUID':'Deal UID'})
    graphJSON3 = json.dumps(fig3, cls=plotly.utils.PlotlyJSONEncoder)

    fig4 = px.line(total_data, x='Date', y=['Total Init Amount', 'Total Expected Amount'], title='<b>Total Expected Valuation</b><br><i>Init Amount AND real amount + expected amount</i>', labels={'value':'Expected', 'variable':'Type'})
    graphJSON4 = json.dumps(fig4, cls=plotly.utils.PlotlyJSONEncoder)

    return render_template('chart.html', 
                           graphJSON1=graphJSON1, graphJSON2=graphJSON2, 
                           graphJSON3=graphJSON3, graphJSON4=graphJSON4, 
                           from_date=from_date_str, to_date=to_date_str, keyword=keyword)

if __name__ == '__main__':
    app.run(debug=True)