import datetime
from typing import List, Sequence, Tuple, Type, Any
from collections import defaultdict

# Import necessary components for SQLAlchemy 2.0 style
from sqlalchemy import Row, create_engine, ForeignKey, select, UniqueConstraint 
from sqlalchemy.orm import (
    relationship, 
    MappedAsDataclass, 
    DeclarativeBase, 
    Mapped, 
    mapped_column,
    Session,
    sessionmaker
)

# Create a SQLite engine
engine = create_engine('sqlite:///tracker.db')

# Define the new Base class for declarative models
# All models will inherit from this, which provides type-hinting support
class Base(MappedAsDataclass, DeclarativeBase):
    """Base class for all models, providing dataclass functionality and DeclarativeBase."""
    pass

# --- MODEL DEFINITIONS ---

class ScrapeJob(Base):
    __tablename__ = 'scrape_jobs'
    __repr_args__ = ['id', 'platform'] # Optional: Helper for __repr__
    
    # Use Mapped[] and mapped_column for type-safe attribute definitions
    platform: Mapped[str | None]
    id: Mapped[int] = mapped_column(primary_key=True, init=False) # init=False for auto-generated PK
    timestamp: Mapped[datetime.datetime] = mapped_column(default_factory=datetime.datetime.now)

    # Relationships are defined using Mapped[List[...]]
    # NOTE: The relationship names MUST be fixed for back_populates to work correctly.
    linkedin_scrapes: Mapped[List["LinkedInScrape"]] = relationship(
        back_populates="scrape_job",
        default_factory=list
    )
    applications: Mapped[List["JobApplication"]] = relationship(
        back_populates="scrape_job", # Must match the attribute name in JobApplication
        default_factory=list
    )


class LinkedInScrape(Base):
    __tablename__ = 'linkedin_scrapes'
    __repr_args__ = ['id', 'search_keywords']
    
    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    scrape_job_id: Mapped[int] = mapped_column(ForeignKey('scrape_jobs.id'))
    search_keywords: Mapped[str | None]
    search_location: Mapped[str | None]
    easy_apply: Mapped[bool]

    # Relationship to ScrapeJob
    scrape_job: Mapped["ScrapeJob"] = relationship(back_populates="linkedin_scrapes")


class JobApplication(Base):
    __tablename__ = 'job_applications'
    # Use the SQLAlchemy 2.0 repr feature
    __repr_args__ = ['job_title', 'company_name']
    
    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    scrape_job_id: Mapped[int] = mapped_column(ForeignKey('scrape_jobs.id')) 
    company_name: Mapped[str | None]
    job_title: Mapped[str | None]
    application_date: Mapped[datetime.datetime | None]
    status: Mapped[str | None]
    job_url: Mapped[str] = mapped_column(unique=True) # Column constraints go inside mapped_column
    job_details: Mapped[str | None]

    # Relationship to ScrapeJob (retains your original name 'scrape_job')
    scrape_job: Mapped["ScrapeJob"] = relationship(
        back_populates="applications" # Must match the attribute name in ScrapeJob
    )
    
    # Relationship to ApplicationFormPage (Fixed relationship names)
    form_pages: Mapped[List["ApplicationFormPage"]] = relationship(
        back_populates="job_application",
        default_factory=list
    )


class ApplicationFormPage(Base):
    __tablename__ = 'application_form_pages'
    
    # Define the composite unique constraint
    __table_args__ = (
        # Ensures that a single job application (job_application_id) 
        # has only one entry for a given page_number.
        UniqueConstraint('job_application_id', 'page_number', name='_job_page_uc'),
    )
    
    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    job_application_id: Mapped[int] = mapped_column(ForeignKey('job_applications.id'))
    page_number: Mapped[int]
    form_page_title: Mapped[str | None]
    form_data: Mapped[str | None]
    timestamp: Mapped[datetime.datetime] = mapped_column(default_factory=datetime.datetime.now)

        # Relationship to JobApplication
    job_application: Mapped["JobApplication"] = relationship(
        back_populates="form_pages",
        default=None)
    
    # Relationship to FormQuestion
    form_questions: Mapped[List["FormQuestion"]] = relationship(
        back_populates="form_page",
        default_factory=list
    )


class FormQuestion(Base):
    __tablename__ = 'form_questions'
    
    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    form_page_id: Mapped[int] = mapped_column(ForeignKey('application_form_pages.id'))
    question_text: Mapped[str | None]
    question_type: Mapped[str | None]

    question_answer_id: Mapped[int | None] = mapped_column(ForeignKey('question_answers.id'), default=None)
    timestamp: Mapped[datetime.datetime] = mapped_column(default_factory=datetime.datetime.now)
    # Relationship to ApplicationFormPage
    form_page: Mapped["ApplicationFormPage"] = relationship(
        back_populates="form_questions",
        default=None
    )
    
    # Relationship to QuestionAnswer (many FormQuestions to one Answer)
    question_answer: Mapped["QuestionAnswer"] = relationship(
        back_populates="form_questions",
        default=None
    )
    

class QuestionAnswer(Base):
    __tablename__ = 'question_answers'
    __repr_args__ = ['id', 'answer_text']
    
    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    answer_text: Mapped[str | None]
    answer_type: Mapped[str | None]  # e.g., 'text', 'multiple_choice', 'file', etc.
    # metadata: Mapped[str | None]  # JSON string for additional data
    timestamp: Mapped[datetime.datetime] = mapped_column(default_factory=datetime.datetime.now)
    
    # Relationship to FormQuestion (one Answer to many FormQuestions)
    form_questions: Mapped[List["FormQuestion"]] = relationship(
        back_populates="question_answer",
        default_factory=list
    )


# Create the tables in the database
Base.metadata.create_all(engine)


def group_scraped_applications_by_platform():
    """
    Queries JobApplication records with status='Scraped', joins with ScrapeJob
    to get the platform, and groups the results.
    """
    
    print("\n--- Querying Scraped Job Applications Grouped by Platform ---")

    # 1. Select the platform and the JobApplication object.
    # 2. Join JobApplication with ScrapeJob using the relationship attribute (aliased to simplify join).
    # 3. Filter by JobApplication.status == 'Scraped'.
    stmt = (
        select(ScrapeJob.platform, JobApplication)
        .join(JobApplication.scrape_job) # Use the relationship attribute for implicit join condition
        .where(JobApplication.status == 'Scraped')
    )

    # Use a dictionary to manually group the results after fetching.
    # SQL's GROUP BY typically aggregates; to get all full objects per group,
    # it's often simpler to filter and then group in Python, or use the ORM's features.
    # Since we need to iterate on groups of *objects*, we fetch all relevant objects and group them manually.
    grouped_applications: defaultdict[str | None, List["JobApplication"]] = defaultdict(list)
    
    with Session(engine) as session:
        # Fetch the platform string and the JobApplication object tuple
        results: Sequence[Row[Tuple[str | None, JobApplication]]] = session.execute(stmt).all()

    # Manually group the results in Python
    for platform, application in results:
        grouped_applications[platform].append(application)
        
    return grouped_applications


class DBOperator:
    """
    A mixin class to provide database synchronization and update methods
    to other classes using SQLAlchemy sessions.
    """
    def __init__(self):
        # Create a new database session
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        self._db_session = SessionLocal()

    def db_sync(self, data_model:Base):
        """Adds or updates a model instance and commits the transaction."""
        self._db_session.add(data_model)
        self._db_session.commit()
        self._db_session.refresh(data_model)

    def db_update(
            self,
            data_model_class:Type[Base],
            match_keys:dict[str,Any], # Use Any for more flexible type
            update_data:dict[str,Any]): # Use Any for more flexible type
        """
        Updates an existing record based on match_keys, or creates a new one 
        if not found, then synchronizes to the database.
        """
        # Use select().filter_by() for flexible lookup
        stmt = select(data_model_class).filter_by(**match_keys)
        existing_record = self._db_session.execute(stmt).scalar_one_or_none()

        if existing_record:
            # Update attributes of the existing record
            for key, value in update_data.items():
                setattr(existing_record, key, value)
            self.db_sync(existing_record)

        else:
            # Create a new record
            # NOTE: We merge match_keys and update_data to create the new record
            # This is essential if match_keys contains values needed for object creation
            new_record_data = {**match_keys, **update_data} 
            new_record = data_model_class(**new_record_data)
            self.db_sync(new_record)
