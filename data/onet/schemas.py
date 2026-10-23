from typing import List, Optional
from pydantic import BaseModel, Field

class Occupation(BaseModel):
    code: str = Field(..., description="O*NET-SOC Code")
    title: str
    description: str = ""

class Skill(BaseModel):
    onet_soc_code: str
    element_id: str
    element_name: Optional[str] = "Essential Skill"
    data_value: float = Field(default=1.0, description="Importance or Level score")
    scale_id: Optional[str] = None

class KnowledgeArea(BaseModel):
    onet_soc_code: str
    element_id: str
    element_name: Optional[str] = "Knowledge Area"
    data_value: float
    scale_id: Optional[str] = None

class EducationRequirement(BaseModel):
    onet_soc_code: str
    element_id: str
    category_description: Optional[str] = "Education Requirement"
    percentage: float = 0.0

class Technology(BaseModel):
    onet_soc_code: str
    commodity_title: str
    hot_technology: bool = False

class CareerProfile(BaseModel):
    occupation: Occupation
    skills: List[Skill] = []
    knowledge: List[KnowledgeArea] = []
    education: List[EducationRequirement] = []
    technologies: List[Technology] = []
