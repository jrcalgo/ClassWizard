import os
import glob
import json
import pandas as pd
from pathlib import Path
from typing import Dict, List
from pydantic import ValidationError
from schemas import Occupation, Skill, KnowledgeArea, EducationRequirement, Technology, CareerProfile

class ONetBatchETL:
    def __init__(self, raw_data_dir: str, output_dir: str):
        self.raw_data_dir = Path(raw_data_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _read_csv(self, file_pattern: str) -> pd.DataFrame:
        """Helper to search recursively and read O*NET comma-separated CSV files."""
        matches = list(self.raw_data_dir.rglob(file_pattern))
        if not matches:
            raise FileNotFoundError(f"No file matching '{file_pattern}' found in {self.raw_data_dir}")
        
        print(f"  -> Reading {matches[0].name}")
        return pd.read_csv(matches[0], sep=",", dtype=str)

    def extract_and_clean_occupations(self) -> pd.DataFrame:
        """Extracts Occupations & Career Descriptions from occupation_data.csv."""
        print("[ETL] Processing Occupations & Descriptions...")
        df = self._read_csv("occupation_data.csv")

        rename_map = {
            "onetsoc_code": "onet_soc_code", "O*NET-SOC Code": "onet_soc_code",
            "title": "title", "Title": "title",
            "description": "description", "Description": "description"
        }
        df = df.rename(columns=rename_map)

        df["onet_soc_code"] = df["onet_soc_code"].astype(str).str.strip()
        df["title"] = df["title"].astype(str).str.strip()
        df["description"] = df["description"].fillna("").astype(str).str.strip()

        df = df.dropna(subset=["onet_soc_code", "title"])
        return df[["onet_soc_code", "title", "description"]]

    def extract_and_clean_skills(self) -> pd.DataFrame:
        """Extracts Essential Skills from essential_skills.csv."""
        print("[ETL] Processing Essential Skills...")
        df = self._read_csv("essential_skills.csv")

        rename_map = {
            "onetsoc_code": "onet_soc_code", "O*NET-SOC Code": "onet_soc_code",
            "element_id": "element_id", "Element ID": "element_id",
            "element_name": "element_name", "Element Name": "element_name",
            "scale_id": "scale_id", "Scale ID": "scale_id",
            "data_value": "data_value", "Data Value": "data_value"
        }
        df = df.rename(columns=rename_map)

        if "data_value" in df.columns:
            df["data_value"] = pd.to_numeric(df["data_value"], errors="coerce")
            df = df.dropna(subset=["onet_soc_code", "data_value"])
        else:
            df["data_value"] = 1.0

        if "element_name" not in df.columns:
            df["element_name"] = df.get("element_id", "Essential Skill")

        if "element_id" not in df.columns:
            df["element_id"] = "ESSENTIAL_SKILL"

        if "scale_id" not in df.columns:
            df["scale_id"] = None

        return df[["onet_soc_code", "element_id", "element_name", "scale_id", "data_value"]]

    def extract_and_clean_knowledge(self) -> pd.DataFrame:
        """Extracts Knowledge Areas from knowledge.csv."""
        print("[ETL] Processing Knowledge Areas...")
        df = self._read_csv("knowledge.csv")

        rename_map = {
            "onetsoc_code": "onet_soc_code", "O*NET-SOC Code": "onet_soc_code",
            "element_id": "element_id", "Element ID": "element_id",
            "element_name": "element_name", "Element Name": "element_name",
            "scale_id": "scale_id", "Scale ID": "scale_id",
            "data_value": "data_value", "Data Value": "data_value"
        }
        df = df.rename(columns=rename_map)

        df["data_value"] = pd.to_numeric(df["data_value"], errors="coerce")
        df = df.dropna(subset=["onet_soc_code", "data_value"])

        if "element_name" not in df.columns:
            df["element_name"] = df.get("element_id", "Knowledge Area")

        if "element_id" not in df.columns:
            df["element_id"] = "KNOWLEDGE"

        if "scale_id" not in df.columns:
            df["scale_id"] = None

        return df[["onet_soc_code", "element_id", "element_name", "scale_id", "data_value"]]

    def extract_and_clean_education(self) -> pd.DataFrame:
        """Extracts Education Requirements from education.csv."""
        print("[ETL] Processing Education Requirements...")
        df = self._read_csv("education.csv")

        rename_map = {
            "onetsoc_code": "onet_soc_code", "O*NET-SOC Code": "onet_soc_code",
            "element_id": "element_id", "Element ID": "element_id",
            "category": "category_description", "Category Description": "category_description",
            "data_value": "percentage", "Data Value": "percentage"
        }
        df = df.rename(columns=rename_map)

        # Filter for Education scale if element_id column exists
        if "element_id" in df.columns:
            df = df[df["element_id"].astype(str).str.startswith("2.E.1", na=False)]
        else:
            df["element_id"] = "EDUCATION"

        if "percentage" in df.columns:
            df["percentage"] = pd.to_numeric(df["percentage"], errors="coerce")
            df = df.dropna(subset=["onet_soc_code", "percentage"])
        else:
            df["percentage"] = 0.0

        if "category_description" not in df.columns:
            df["category_description"] = df.get("element_id", "Education Requirement")

        return df[["onet_soc_code", "element_id", "category_description", "percentage"]]

    def extract_and_clean_technologies(self) -> pd.DataFrame:
        """Extracts Software & Technologies from software_skills.csv."""
        print("[ETL] Processing Software Skills...")
        df = self._read_csv("software_skills.csv")

        rename_map = {
            "onetsoc_code": "onet_soc_code", "O*NET-SOC Code": "onet_soc_code",
            "example": "commodity_title", "Example": "commodity_title",
            "software_name": "commodity_title", "Software": "commodity_title",
            "hot_technology": "hot_technology", "Hot Technology": "hot_technology"
        }
        df = df.rename(columns=rename_map)

        if "commodity_title" not in df.columns:
            # Fallback for columns containing skill/tool names
            potential_cols = [c for c in df.columns if "title" in c or "name" in c or "skill" in c]
            if potential_cols:
                df["commodity_title"] = df[potential_cols[0]]
            else:
                df["commodity_title"] = "Unknown Software"

        if "hot_technology" not in df.columns:
            df["hot_technology"] = False
        else:
            df["hot_technology"] = df["hot_technology"].astype(str).str.upper().map({"Y": True, "N": False}).fillna(False)

        df = df.dropna(subset=["onet_soc_code", "commodity_title"])
        return df[["onet_soc_code", "commodity_title", "hot_technology"]]

    def run_pipeline(self):
        """Executes full ETL extraction, joins profiles, and validates schemas."""
        occupations_df = self.extract_and_clean_occupations()
        skills_df = self.extract_and_clean_skills()
        knowledge_df = self.extract_and_clean_knowledge()
        education_df = self.extract_and_clean_education()
        tech_df = self.extract_and_clean_technologies()

        # Save clean relational tables
        occupations_df.to_csv(self.output_dir / "clean_occupations.csv", index=False)
        skills_df.to_csv(self.output_dir / "clean_skills.csv", index=False)
        knowledge_df.to_csv(self.output_dir / "clean_knowledge.csv", index=False)
        education_df.to_csv(self.output_dir / "clean_education.csv", index=False)
        tech_df.to_csv(self.output_dir / "clean_technologies.csv", index=False)

        print(f"[ETL] Clean relational CSV tables written to {self.output_dir}/")

        # Nested Document Assembly for NoSQL / Graph Ingestion
        print("[ETL] Assembling unified career profiles...")
        profiles = []
        for idx, occ in occupations_df.iterrows():
            code = occ["onet_soc_code"]

            occ_skills = skills_df[skills_df["onet_soc_code"] == code].to_dict(orient="records")
            occ_knowledge = knowledge_df[knowledge_df["onet_soc_code"] == code].to_dict(orient="records")
            occ_edu = education_df[education_df["onet_soc_code"] == code].to_dict(orient="records")
            occ_tech = tech_df[tech_df["onet_soc_code"] == code].to_dict(orient="records")

            profile_data = {
                "occupation": {
                    "code": occ["onet_soc_code"],
                    "title": occ["title"],
                    "description": occ["description"]
                },
                "skills": occ_skills,
                "knowledge": occ_knowledge,
                "education": occ_edu,
                "technologies": occ_tech
            }

            try:
                validated_profile = CareerProfile(**profile_data)
                profiles.append(validated_profile.model_dump_json())
            except ValidationError as e:
                print(f"Validation error for SOC Code {code}: {e}")

        # Write out unified JSONL dataset
        jsonl_path = self.output_dir / "onet_unified_profiles.jsonl"
        with open(jsonl_path, "w", encoding="utf-8") as f:
            f.write("\n".join(profiles))

        print(f"[ETL] Complete! Unified JSONL written to {jsonl_path}")

if __name__ == "__main__":
    RAW_DATA_DIRECTORY = "./raw_onet_data/db_31_0_csv"
    OUTPUT_DIRECTORY = "./processed_onet_data"

    pipeline = ONetBatchETL(raw_data_dir=RAW_DATA_DIRECTORY, output_dir=OUTPUT_DIRECTORY)
    pipeline.run_pipeline()
