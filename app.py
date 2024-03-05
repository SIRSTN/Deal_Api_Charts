from flask import Flask, render_template
import plotly
import plotly.express as px
import pandas as pd
from pymongo import MongoClient
import json
from configparser import ConfigParser

app = Flask(__name__)

# Load configuration file
config = ConfigParser()
config.read('config.ini')

# Setup MongoDB Client
#client = MongoClient(config.get('DEAL_API_VALUATION', 'MongoClient'))
client = MongoClient("mongodb://localhost:27017/")
db = client['Deal_Transactions']

def get_total_valations():
    result = db["Valuations"].aggregate([
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
    ])
    return pd.DataFrame(list(result))

def get_deal_valations():
    valuations = list(db["Valuations"].find({}, {'Date': 1, 'DealUID': 1, 'Volume': 1, 'Sold_Volume': 1, 'Init_Volume': 1, 'Price': 1}))
    for valuation in valuations:
        valuation['Sold_Volume'] = float(valuation.get('Sold_Volume', 0)) * 1.05
        valuation['DealExpectedVolume'] = valuation['Volume'] + valuation['Sold_Volume'] - valuation.get('Init_Volume', 0)
    return pd.DataFrame(valuations)

@app.route('/')
def index():
    total_data = get_total_valations()
    total_data.rename(columns={
        '_id': 'Date',
        'TotalRealVolume': 'Total Real Volume',
        'TotalInitVolume': 'Total Init Volume',
        'TotalEffectiveVolume': 'Total Effective Volume',
        'TotalExpectedVolume': 'Total Expected Volume',
        'TotalInitAmount': 'Total Init Amount',
        'TotalExpectedAmount': 'Total Expected Amount'
    }, inplace=True)
    
    deal_data = get_deal_valations()
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

    return render_template('chart.html', graphJSON1=graphJSON1, graphJSON2=graphJSON2, graphJSON3=graphJSON3, graphJSON4=graphJSON4)

if __name__ == '__main__':
    app.run(debug=True)
