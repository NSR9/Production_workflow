from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
from typing import List, Optional
from pymongo import MongoClient
from datetime import datetime
from bson.objectid import ObjectId

from production_workflow.workflow import ProductionGraph

app = FastAPI(title="Stage-Centric Production Workflow API")

# MongoDB setup
MONGO_URI = "mongodb://localhost:27017/"
client = MongoClient(MONGO_URI)
db = client["production_workflow_db"]
workflows_collection = db["stage_workflows"]

# Pydantic Models
class WastageEntry(BaseModel):
    goodName: str
    wastage: float
    wastageType: str

class GoodEntry(BaseModel):
    goodName: str
    quantity: float
    unit: str

class ProductionDetails(BaseModel):
    wastageEntries: List[WastageEntry]
    productionTime: str
    outsource: str

class Stage(BaseModel):
    stageNumber: int
    rawGoods: List[GoodEntry]
    outputGoods: List[GoodEntry]
    productionDetails: ProductionDetails

class StageWorkflowCreate(BaseModel):
    name: str
    description: Optional[str]
    productionStages: List[Stage]

class StageWorkflowResponse(StageWorkflowCreate):
    id: str
    created_at: datetime

# Helper


# API Routes
@app.get("/")
async def read_root():
    return {"message": "Production Workflow API"}

@app.post("/workflows", response_model=StageWorkflowResponse, status_code=status.HTTP_201_CREATED)
async def create_stage_workflow(workflow: StageWorkflowCreate):
    try:
        graph = ProductionGraph()
        graph.load_from_json(workflow.dict())
        graph.link_stages()

        workflow_dict = workflow.dict()
        workflow_dict["created_at"] = datetime.now()

        result = workflows_collection.insert_one(workflow_dict)
        return {**workflow_dict, "id": str(result.inserted_id)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating workflow: {str(e)}")

@app.get("/workflows", response_model=List[StageWorkflowResponse])
async def list_workflows():
    workflows = []
    for wf in workflows_collection.find():
        wf["id"] = str(wf.pop("_id"))
        workflows.append(wf)
    return workflows

@app.get("/workflows/{workflow_id}", response_model=StageWorkflowResponse)
async def get_workflow(workflow_id: str):
    try:
        workflow = workflows_collection.find_one({"_id": ObjectId(workflow_id)})
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")
        workflow["id"] = str(workflow.pop("_id"))
        return workflow
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving workflow: {str(e)}")

@app.get("/workflows/{workflow_id}/dependencies/{finished_good}")
async def get_dependencies(workflow_id: str, finished_good: str):
    try:
        workflow = workflows_collection.find_one({"_id": ObjectId(workflow_id)})
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")

        graph = ProductionGraph()
        graph.load_from_json(workflow)
        graph.link_stages()
        fg_node = next((n for n in graph.goods if n.name == finished_good and n.is_finished), None)
        if not fg_node:
            raise HTTPException(status_code=404, detail=f"Finished good '{finished_good}' not found")

        raw_deps = set()
        def trace_raws(node):
            for parent in node.made_from:
                if parent.good_type == "Raw":
                    raw_deps.add((parent.name, parent.quantity, parent.unit))
                else:
                    trace_raws(parent)

        trace_raws(fg_node)
        return {
            "finished_good": finished_good,
            "raw_dependencies": [
                {"name": name, "quantity": qty, "unit": unit} for name, qty, unit in sorted(raw_deps)
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error tracing dependencies: {str(e)}")

@app.get("/workflows/{workflow_id}/display")
async def display_workflow(workflow_id: str):
    try:
        workflow = workflows_collection.find_one({"_id": ObjectId(workflow_id)})
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")

        graph = ProductionGraph()
        graph.load_from_json(workflow)
        graph.link_stages()
        response = []
        for num in sorted(graph.stages):
            stage = graph.stages[num]
            response.append({
                "stageNumber": num,
                "productionTime": stage.production_time,
                "outsource": stage.outsource,
                "wastageEntries": stage.wastage_entries,
                "rawGoods": [
                    {"name": g.name, "quantity": g.quantity, "unit": g.unit}
                    for g in stage.raw_inputs
                ],
                "intermediaryGoods": [
                    {
                        "name": g.name,
                        "quantity": g.quantity,
                        "unit": g.unit,
                        "from": [p.name for p in g.made_from]
                    }
                    for g in stage.outputs
                ]
            })
        return {"stages": response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error displaying workflow: {str(e)}")
