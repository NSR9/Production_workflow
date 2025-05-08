from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
from pymongo import MongoClient
import sys
import os
from datetime import datetime

# Add the production_workflow directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'production_workflow'))

# Import the ProductionGraph class from workflow.py
from workflow import ProductionGraph

app = FastAPI(title="Production Workflow API")

# MongoDB Connection
# Replace with your MongoDB connection string if needed
MONGO_URI = "mongodb://localhost:27017/"
client = MongoClient(MONGO_URI)
db = client["production_workflow_db"]
workflows_collection = db["workflows"]

# Pydantic models for request validation
class GoodBase(BaseModel):
    name: str
    
class RawGood(GoodBase):
    good_type: str = "Raw"
    
class IntermediaryGood(GoodBase):
    good_type: str = "Intermediary"
    stage: int
    
class FinishedGood(GoodBase):
    good_type: str = "Finished"
    
class Link(BaseModel):
    source: str
    target: str
    quantity: Optional[float] = None
    unit: Optional[str] = None
    
class ProductionWorkflowCreate(BaseModel):
    name: str
    description: Optional[str] = None
    raw_goods: List[RawGood]
    intermediary_goods: List[IntermediaryGood]
    finished_goods: List[FinishedGood]
    links: List[Link]

class ProductionWorkflowResponse(ProductionWorkflowCreate):
    id: str
    created_at: datetime
    
@app.get("/")
async def read_root():
    return {"message": "Production Workflow API"}

@app.post("/workflows", response_model=ProductionWorkflowResponse, status_code=status.HTTP_201_CREATED)
async def create_workflow(workflow: ProductionWorkflowCreate):
    try:
        # Create a ProductionGraph instance
        graph = ProductionGraph()
        
        # Add raw goods
        for good in workflow.raw_goods:
            graph.add_good(good.name, good.good_type)
            
        # Add intermediary goods
        for good in workflow.intermediary_goods:
            graph.add_good(good.name, good.good_type, stage=good.stage)
            
        # Add finished goods
        for good in workflow.finished_goods:
            graph.add_good(good.name, good.good_type)
            
        # Add links
        for link in workflow.links:
            graph.link(link.source, link.target, link.quantity, link.unit)
        
        # Convert the workflow to a dictionary for MongoDB
        workflow_dict = workflow.dict()
        workflow_dict["created_at"] = datetime.now()
        
        # Insert into MongoDB
        result = workflows_collection.insert_one(workflow_dict)
        
        # Return the created workflow with the MongoDB ID
        response = {**workflow_dict, "id": str(result.inserted_id)}
        return response
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")

@app.get("/workflows", response_model=List[ProductionWorkflowResponse])
async def get_workflows():
    workflows = []
    for workflow in workflows_collection.find():
        workflow["id"] = str(workflow.pop("_id"))
        workflows.append(workflow)
    return workflows

@app.get("/workflows/{workflow_id}", response_model=ProductionWorkflowResponse)
async def get_workflow(workflow_id: str):
    from bson.objectid import ObjectId
    
    try:
        workflow = workflows_collection.find_one({"_id": ObjectId(workflow_id)})
        if workflow:
            workflow["id"] = str(workflow.pop("_id"))
            return workflow
        raise HTTPException(status_code=404, detail=f"Workflow with ID {workflow_id} not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
