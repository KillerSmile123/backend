# graph_data.py

road_graph = {
    "FireStation": {
        "Junction1": 1.2,
        "Junction2": 2.5
    },
    "Junction1": {
        "FireStation": 1.2,
        "Accident": 3.1
    },
    "Junction2": {
        "FireStation": 2.5,
        "Accident": 1.8
    },
    "Accident": {
        "Junction1": 3.1,
        "Junction2": 1.8
    }
}
