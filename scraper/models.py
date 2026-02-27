from pydantic import BaseModel, Field
from typing import List, Optional

class BasicProfile(BaseModel):
    profile_url: str
    full_name: str
    headline: Optional[str] = None
    profile_picture: Optional[str] = None
    location: Optional[str] = None
    connection_count: Optional[int] = None
    follower_count: Optional[int] = None

class Experience(BaseModel):
    company: str
    role: str
    employment_type: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    duration: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None

class Education(BaseModel):
    institute: str
    degree: Optional[str] = None
    field_of_study: Optional[str] = None
    start_year: Optional[str] = None
    end_year: Optional[str] = None
    grade: Optional[str] = None
    activities: Optional[str] = None

class ContactInfo(BaseModel):
    email: Optional[str] = None
    phone: Optional[str] = None
    websites: Optional[List[str]] = Field(default_factory=list)
    social_links: Optional[List[str]] = Field(default_factory=list)
    birthday: Optional[str] = None
    connected_at: Optional[str] = None

class Skill(BaseModel):
    name: str

class Certification(BaseModel):
    name: str
    issuer: Optional[str] = None
    issue_date: Optional[str] = None
    expiration_date: Optional[str] = None
    credential_id: Optional[str] = None
    credential_url: Optional[str] = None

class Project(BaseModel):
    name: str
    description: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    url: Optional[str] = None

class ProfileMetadata(BaseModel):
    scraped_at: str
    total_profiles: int
    status: str

class ProfileData(BaseModel):
    profile_url: str
    basic: BasicProfile
    about: Optional[str] = None
    experience: List[Experience] = Field(default_factory=list)
    education: List[Education] = Field(default_factory=list)
    skills: List[Skill] = Field(default_factory=list)
    certifications: List[Certification] = Field(default_factory=list)
    projects: List[Project] = Field(default_factory=list)
    contact_info: Optional[ContactInfo] = None
    
    # Placeholders for other sections
    publications: List[dict] = Field(default_factory=list)
    honors_and_awards: List[dict] = Field(default_factory=list)
    volunteering: List[dict] = Field(default_factory=list)
    courses: List[dict] = Field(default_factory=list)
    languages: List[dict] = Field(default_factory=list)

class FinalOutput(BaseModel):
    metadata: ProfileMetadata
    profiles: List[ProfileData]
