flowchart LR
    subgraph client[🧑 Client]
        direction LR
        CLIENT["GET /admin/cost/overview"]
    end
    subgraph route[🚏 Route 层]
        direction LR
        cost_overview["cost_overview"]
    end
    subgraph service[⚙️ Service 层]
        direction LR
        get["get"]
        overview["overview"]
    end
    subgraph db[🗄️ Database]
        direction LR
        TBL_tasks["📋 tasks
(UNKNOWN)"]
    end
    CLIENT --> cost_overview
    cost_overview --> get
    get --> overview
    overview --> TBL_tasks