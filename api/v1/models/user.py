from datetime import datetime, timezone
from typing import Literal, Optional
from bson import ObjectId
from pymongo.errors import DuplicateKeyError
from api.v1.utils.database import get_collection
from api.v1.utils.logger import get_logger

logger = get_logger("user_model")

COLLECTION_NAME = "users"


class User:
    def __init__(
        self,
        github_id: int,
        username: str,
        email: Optional[str] = None,
        name: Optional[str] = None,
        avatar_url: Optional[str] = None,
        public_repos: Optional[int] = None,
        followers: Optional[int] = None,
        following: Optional[int] = None,
        private_repos: Optional[int] = None,
        cadence: Literal["daily", "weekly", "bi-weekly", "monthly"] = "weekly",
        tone: Literal["formal", "informal", "casual"] = "formal",
        emojis: bool = False,
        hashtags: bool = True,
        github_access_token: Optional[str] = None,
        github_token_expires_at: Optional[datetime] = None,
        github_refresh_token: Optional[str] = None,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
        _id: Optional[str] = None,
    ):
        self._id = _id
        self.github_id = github_id
        self.username = username
        self.email = email
        self.name = name
        self.avatar_url = avatar_url
        self.public_repos = public_repos
        self.followers = followers
        self.following = following
        self.private_repos = private_repos
        self.cadence = cadence
        self.tone = tone
        self.emojis = emojis
        self.hashtags = hashtags
        self.github_access_token = github_access_token
        self.github_token_expires_at = github_token_expires_at
        self.github_refresh_token = github_refresh_token
        self.created_at = created_at or datetime.now(timezone.utc)
        self.updated_at = updated_at or datetime.now(timezone.utc)

    def to_dict(self) -> dict:
        data = {
            "github_id": self.github_id,
            "username": self.username,
            "email": self.email,
            "name": self.name,
            "avatar_url": self.avatar_url,
            "public_repos": self.public_repos,
            "followers": self.followers,
            "following": self.following,
            "private_repos": self.private_repos,
            "cadence": self.cadence,
            "tone": self.tone,
            "emojis": self.emojis,
            "hashtags": self.hashtags,
            "github_access_token": self.github_access_token,
            "github_token_expires_at": self.github_token_expires_at,
            "github_refresh_token": self.github_refresh_token,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if self._id:
            data["_id"] = self._id
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "User":
        """Create User instance from MongoDB document."""
        return cls(
            _id=str(data.get("_id", "")),
            github_id=data["github_id"],
            username=data["username"],
            email=data.get("email"),
            name=data.get("name"),
            avatar_url=data.get("avatar_url"),
            public_repos=data.get("public_repos"),
            followers=data.get("followers"),
            following=data.get("following"),
            private_repos=data.get("private_repos"),
            cadence=data.get("cadence"),
            tone=data.get("tone"),
            emojis=data.get("emojis"),
            hashtags=data.get("hashtags"),
            github_access_token=data.get("github_access_token"),
            github_token_expires_at=data.get("github_token_expires_at"),
            github_refresh_token=data.get("github_refresh_token"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )

    @staticmethod
    async def create_indexes():
        collection = get_collection(COLLECTION_NAME)
        try:
            await collection.create_index("github_id", unique=True)
            await collection.create_index("username")
            logger.info("User collection indexes created successfully")
        except Exception as e:
            logger.error("Failed to create user indexes", extra={"error": str(e)})

    @staticmethod
    async def find_by_github_id(github_id: int) -> Optional["User"]:
        collection = get_collection(COLLECTION_NAME)
        try:
            document = await collection.find_one({"github_id": github_id})
            if document:
                return User.from_dict(document)
            return None
        except Exception as e:
            logger.error(
                "Failed to find user by GitHub ID",
                extra={"github_id": github_id, "error": str(e)},
            )
            raise

    @staticmethod
    async def find_by_id(user_id: str) -> Optional["User"]:
        from bson import ObjectId

        collection = get_collection(COLLECTION_NAME)
        try:
            document = await collection.find_one({"_id": ObjectId(user_id)})
            if document:
                return User.from_dict(document)
            return None
        except Exception as e:
            logger.error(
                "Failed to find user by ID", extra={"user_id": user_id, "error": str(e)}
            )
            raise

    async def save(self) -> "User":
        collection = get_collection(COLLECTION_NAME)
        self.updated_at = datetime.now(timezone.utc)

        try:
            if self._id:
                # Update existing user
                result = await collection.update_one(
                    {"_id": ObjectId(self._id)}, {"$set": self.to_dict()}
                )
                if result.matched_count == 0:
                    raise ValueError(f"User with ID {self._id} not found")
            else:
                # Insert new user
                self.created_at = datetime.utcnow()
                result = await collection.insert_one(self.to_dict())
                self._id = str(result.inserted_id)

            logger.info(
                "User saved successfully",
                extra={"github_id": self.github_id, "username": self.username},
            )
            return self
        except DuplicateKeyError as e:
            logger.error(
                "Duplicate GitHub ID",
                extra={"github_id": self.github_id, "error": str(e)},
            )
            raise ValueError(f"User with GitHub ID {self.github_id} already exists")
        except Exception as e:
            logger.error(
                "Failed to save user",
                extra={"github_id": self.github_id, "error": str(e)},
            )
            raise

    async def update_github_token(
        self,
        access_token: str,
        expires_at: Optional[datetime] = None,
        refresh_token: Optional[str] = None,
    ) -> "User":
        self.github_access_token = access_token
        self.github_token_expires_at = expires_at
        if refresh_token:
            self.github_refresh_token = refresh_token
        return await self.save()
