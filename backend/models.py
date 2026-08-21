"""Database models for the backend.

Reuses the same SQLite database as ai_teacher.storage.models, but adds:
  - User        (WeChat openid, role: parent/teacher)
  - Classroom   (teacher-owned)
  - Membership  (parent joins a class with their child's name)
  - Homework.submit_user, Homework.classroom (links to the above)

We bind to the same peewee database defined in ai_teacher.storage.models
so we don't split data across multiple files.
"""

from __future__ import annotations

from datetime import datetime

from peewee import (
    AutoField,
    CharField,
    DateTimeField,
    ForeignKeyField,
    TextField,
)

from ai_teacher.storage.models import Homework, db


# --------- New tables ---------

class User(db.Model):
    """A WeChat user. Can be parent or teacher."""

    id = AutoField()
    openid = CharField(unique=True, index=True)
    role = CharField()  # 'parent' or 'teacher'
    name = CharField()
    avatar_url = CharField(null=True)
    created_at = DateTimeField(default=datetime.now)
    last_login = DateTimeField(null=True)

    class Meta:
        table_name = "user"


class Classroom(db.Model):
    """A class owned by a teacher. Parents join with a code."""

    id = AutoField()
    name = CharField()
    code = CharField(unique=True, index=True)  # 6-digit
    teacher = ForeignKeyField(User, backref="classes_teaching", on_delete="CASCADE")
    created_at = DateTimeField(default=datetime.now)

    class Meta:
        table_name = "classroom"


class Membership(db.Model):
    """A parent's enrollment in a class. Stores the child name they uploaded for."""

    id = AutoField()
    user = ForeignKeyField(User, backref="memberships", on_delete="CASCADE")
    classroom = ForeignKeyField(Classroom, backref="memberships", on_delete="CASCADE")
    child_name = CharField()
    created_at = DateTimeField(default=datetime.now)

    class Meta:
        table_name = "membership"
        indexes = ((("user", "classroom"), True),)  # unique


class AuthToken(db.Model):
    """Simple bearer-token table. The mini program stores the token in storage."""

    id = AutoField()
    token = CharField(unique=True, index=True)
    user = ForeignKeyField(User, backref="tokens", on_delete="CASCADE")
    created_at = DateTimeField(default=datetime.now)
    expires_at = DateTimeField(null=True)

    class Meta:
        table_name = "auth_token"


# --------- Augment existing Homework ---------
# Peewee allows adding new fields to an existing model by re-declaring them.
# We re-declare here to add the FK columns; SQL is auto-handled by create_tables.
def _patch_homework() -> None:
    fk_fields = {
        "submit_user": ForeignKeyField(User, null=True, backref="submissions", on_delete="SET NULL"),
        "classroom": ForeignKeyField(Classroom, null=True, backref="homeworks", on_delete="SET NULL"),
    }
    for name, field in fk_fields.items():
        if name not in Homework._meta.fields:
            Homework._meta.add_field(name, field)


_patch_homework()


ALL_NEW_TABLES = [User, Classroom, Membership, AuthToken]
