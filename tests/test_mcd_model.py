import datetime
import io
import logging
from typing import List, Dict, Mapping, Any

import mongomock.mongo_client
import pytest
import pytz
from bson import ObjectId
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError

from dal import mcd_model, db_utils, mcd_import
from dal.mcd_model import initialize_collections
from notifications.email_sender import EmailSenderInterface
from notifications.notifier import Notifier

_TEST_DB_NAME = "_licco_test_db_"

client: MongoClient[Mapping[str, Any]]


def create_test_db_client():
    try:
        # NOTE: short timeout so that switch to mongomock is fast
        db_client = db_utils.create_mongo_client(timeout=500)
        # this ping is necessary for checking the connection,
        # as the client is only connected on the first db call
        db_client.admin.command('ping')
        print("\n==== MongoDb is connected ====\n")
        return db_client
    except ServerSelectionTimeoutError:
        # mongo db is not connected (maybe it doesn't even exist on this system)
        # therefore we switch to mongo mock in order to mock db calls
        print("\n==== MongoDb is not connected, switching to MongoMock ====\n")
        db_client = mongomock.mongo_client.MongoClient()
        return db_client
    except Exception as e:
        print("\nFailed to create a mongodb client for tests:\n")
        raise e

@pytest.fixture(scope="session")
def db():
    """Create db at the start of the session"""
    global client
    client = create_test_db_client()
    db = client[_TEST_DB_NAME]
    initialize_collections(db)

    # we expect a fresh test database to only have 1 project (master project)
    projects = list(db['projects'].find())
    assert len(projects) == 1, "only one project should be present (master project)"
    assert projects[0]['name'] == "LCLS Machine Configuration Database", "expected a master project"

    # roles used in tests
    admin_users = {"app": "Licco", "name": "Admin", "players": ["uid:admin_user"], "privileges": ["read", "write", "edit", "approve", "admin"]}
    approvers = {"app": "Licco", "name": "Approver", "players": ["uid:approve_user"], "privileges": ["read", "write", "edit", "approve"]}
    super_approvers = {"app": "Licco", "name": "Super Approver", "players": ["uid:super_approver"], "privileges": ["read", "write", "edit", "approve", "super_approve"]}
    editors = {"app": "Licco", "name": "Editor", "players": ["uid:editor_user", "uid:editor_user_2"], "privileges": ["read", "write", "edit"]}
    res = db['roles'].insert_many([admin_users, approvers, super_approvers, editors])
    assert len(res.inserted_ids) == 4, "roles should be inserted"

    # ffts used in tests
    ffts = [{"fc": "TESTFC", "fc_desc": "fcDesc", "fg": "TESTFG", "fg_desc": "fgDesc"}]
    for f in ffts:
        ok, err, fft = mcd_model.create_new_fft(db, f['fc'], f['fg'], f.get('fc_desc', ''), f.get('fg_desc', ''))
        assert ok, f"fft '{f['fc']}' could not be inserted due to: {err}"

    return db

@pytest.fixture(scope="session", autouse=True)
def destroy_db():
    """Destroy db and its data at the end of the testing session"""
    yield
    global client
    if client:
        client.drop_database(_TEST_DB_NAME)
        client.close()


class TestEmailSender(EmailSenderInterface):
    """Testing email sender, so we can verify whether the emails were correctly assigned"""
    def __init__(self):
        self.emails_sent = []

    def send_email(self, from_user: str, to_users: List[str], subject: str, content: str,
                   plain_text_content: str = "", send_as_separate_emails: bool = True):
            self.emails_sent.append({'from': from_user, 'to': sorted(to_users), 'subject': subject, 'content': content})

    def validate_email(self, username_or_email: str):
        if username_or_email == 'invalid_user@example.com':
            # an invalid account used for testing
            return False
        return True

    def clear(self):
        self.emails_sent = []


class NoOpEmailSender(EmailSenderInterface):
    def __init__(self):
        pass

class NoOpNotifier(Notifier):
    def __init__(self):
        super().__init__('', NoOpEmailSender(), "admin@example.com")
        pass

    def send_email_notification(self, receivers: List[str], subject: str, html_msg: str,
                                plain_text_msg: str = ""):
        # do nothing
        pass

# -------- helper functions --------

def create_project(db, project_name, owner, editors: List[str] = None, approvers: List[str] = None) -> Dict[str, any]:
    if not editors:
        editors = []
    if not approvers:
        approvers = []

    # TODO: create project should probably accept editors and approvers as well, we would have to verify them though
    project = mcd_model.create_new_project(db, project_name, "", owner)
    if editors or approvers:
        mcd_model.update_project_details(db, owner, project['_id'], {'editors': editors, 'approvers': approvers}, NoOpNotifier())
    assert project, "project should be created but it was not"
    return project


# -------- tests ---------

def test_create_delete_project(db):
    """test project creation and deletion.
    A regular user can't delete a project, but only hide it via a status flag (status == hidden)
    """
    project = mcd_model.create_new_project(db, "test_create_delete_project", "my description", "test_user")
    assert project, "project should be created"
    assert len(str(project["_id"])) > 0, "Project id should exist"
    assert project["description"] == "my description", "wrong description inserted"
    assert len(project["editors"]) == 0, "no editors should be there"
    assert len(project["approvers"]) == 0, "no approvers should be there"

    projects = list(db["projects"].find({"name": "test_create_delete_project"}))
    assert len(projects) == 1, "Only one such project should be found"

    prj = projects[0]
    assert prj["owner"] == "test_user", "wrong project owner set"
    assert prj["status"] == "development", "newly created project should be in development"
    ok, err = mcd_model.delete_project(db, "test_user", prj["_id"])
    assert err == "", "there should be no error"
    assert ok

    # regular user can't delete a project, only hide it
    found_after_delete = list(db["projects"].find({"name": "test_create_delete_project"}))
    assert len(found_after_delete) == 1, "project should not be deleted"
    assert found_after_delete[0]['status'] == 'hidden', "project should be hidden"


@pytest.mark.skip(reason="TODO: implement this test case")
def test_create_delete_project_admin(db):
    """test project creation and deletion for an admin user
    As opposed to the regular user, the admin user can delete a project and all its device values
    """
    # TODO: check that project and all its fft fields (such as comments) are properly deleted when admin
    # deletes the project
    pass


def test_add_fft_to_project(db):
    # TODO: check what happens if non editor is trying to update fft: we should return an error
    project = mcd_model.create_new_project(db, "test_add_fft_to_project", "", "test_user")

    # get ffts for project, there should be none
    project_ffts = mcd_model.get_project_ffts(db, project["_id"])
    assert len(project_ffts) == 0, "there should be no ffts in a new project"

    # add fft change
    fft_id = str(mcd_model.get_fft_id_by_names(db, "TESTFC", "TESTFG"))
    assert fft_id, "fft_id should exist"
    fft_update = {'_id': fft_id, 'comments': 'some comment', 'nom_ang_x': 1.23}
    ok, err, update_status = mcd_model.update_fft_in_project(db, "test_user", project["_id"], fft_update)
    assert err == "", "there should be no error"
    assert ok, "fft should be inserted"

    project_ffts = mcd_model.get_project_ffts(db, project["_id"])
    assert len(project_ffts) == 1, "we should have at least 1 fft inserted"

    inserted_fft = project_ffts[fft_id]
    assert str(inserted_fft["fft"]["_id"]) == fft_update["_id"]
    assert inserted_fft["comments"] == fft_update["comments"]
    assert inserted_fft["nom_ang_x"] == pytest.approx(fft_update["nom_ang_x"], "0.001")
    assert len(inserted_fft["discussion"]) == 0, "there should be no discussion comments"
    # discussion and fft are extra fields
    default_fields = 2
    inserted_fields = 2
    total_fields = default_fields + inserted_fields
    assert len(inserted_fft.keys()) == total_fields, "there should not be more fields than the one we have inserted"


def test_remove_fft_from_project(db):
    project = mcd_model.create_new_project(db, "test_remove_fft_from_project", "", "test_user")
    prjid = str(project["_id"])

    # insert new fft
    fft_id = str(mcd_model.get_fft_id_by_names(db, "TESTFC", "TESTFG"))
    fft_update = {'_id': fft_id, 'nom_ang_y': 1.23}
    ok, err, update_status = mcd_model.update_fft_in_project(db, "test_user", prjid, fft_update)
    assert err == ""
    assert ok

    inserted_ffts = mcd_model.get_project_ffts(db, prjid)
    assert len(inserted_ffts) == 1
    inserted_fft = inserted_ffts[fft_id]
    assert str(inserted_fft["fft"]["_id"]) == fft_update["_id"]

    # remove inserted fft
    ok, err = mcd_model.remove_ffts_from_project(db, "test_user", prjid, [fft_id])
    assert err == ""
    assert ok

    project_ffts = mcd_model.get_project_ffts(db, prjid)
    assert len(project_ffts) == 0, "there should be no ffts after deletion"


def test_get_project_ffts(db):
    project = mcd_model.create_new_project(db, "test_get_project_ffts", "", "test_user")
    prjid = str(project["_id"])

    # insert new fft
    fft_id = str(mcd_model.get_fft_id_by_names(db, "TESTFC", "TESTFG"))
    fft_update = {'_id': fft_id, 'nom_ang_y': 1.23, 'nom_ang_x': 2.31}
    ok, err, update_status = mcd_model.update_fft_in_project(db, "test_user", prjid, fft_update)
    assert err == ""
    assert ok

    inserted_ffts = mcd_model.get_project_ffts(db, prjid)
    assert len(inserted_ffts) == 1

    fft = inserted_ffts[fft_id]
    assert fft['nom_ang_y'] == 1.23
    assert fft['nom_ang_x'] == 2.31
    assert fft.get('nom_ang_z', None) is None

    # check what is stored in the database, we should find only the values that we have stored
    changes = list(db['projects_history'].find({'fft': ObjectId(fft_id), 'prj': ObjectId(prjid)}))
    for change in changes:
        assert change['user'] == "test_user", f"expected something else for change: {change}"
        assert str(change['prj']) == prjid, f"wrong project id; change: {change}"
    assert len(changes) == 2, "we made only 2 value changes, so only 2 value changes should be present in db"


def test_get_project_ffts_after_timestamp(db):
    """Only fetch the ffts inserted after a certain timestamp"""
    project = mcd_model.create_new_project(db, "test_get_project_ffts_after_timestamp", "", "test_user")
    prjid = str(project["_id"])

    # insert new fft
    timestamp = datetime.datetime.now(tz=pytz.UTC) - datetime.timedelta(seconds=1)
    fft_id = str(mcd_model.get_fft_id_by_names(db, "TESTFC", "TESTFG"))
    fft_update = {'_id': fft_id, 'nom_ang_y': 1.23}
    ok, err, update_status = mcd_model.update_fft_in_project(db, "test_user", prjid, fft_update)
    assert err == ""
    assert ok

    ffts = mcd_model.get_project_ffts(db, prjid, asoftimestamp=timestamp)
    assert len(ffts) == 0, "there should be no fft before insertion"

    timestamp = datetime.datetime.now(tz=pytz.UTC)
    ffts = mcd_model.get_project_ffts(db, prjid, asoftimestamp=timestamp)
    assert len(ffts) == 1, "there should be 1 fft insert"

    fft = ffts[fft_id]
    assert fft['nom_ang_y'] == 1.23
    assert fft.get('nom_ang_x', None) is None


def test_project_approval_workflow(db):
    # testing happy path
    project = mcd_model.create_new_project(db, "test_approval_workflow", "", "test_user")
    prjid = project["_id"]

    email_sender = TestEmailSender()
    notifier = Notifier('', email_sender, 'admin@example.com')
    ok, err = mcd_model.update_project_details(db, "test_user", prjid, {'editors': ['editor_user', 'editor_user_2']}, notifier)
    assert err == ""
    assert ok

    # check if notifications were sent (editor should receive an email when assigned)
    assert len(email_sender.emails_sent) == 1, "Editor should receive a notification that they were appointed"
    editor_mail = email_sender.emails_sent[0]
    assert editor_mail['to'] == ['editor_user', 'editor_user_2']
    assert editor_mail['subject'] == 'You were selected as an editor for the project test_approval_workflow'
    email_sender.clear()

    # an editor user should be able to save an fft
    fftid = str(mcd_model.get_fft_id_by_names(db, "TESTFC", "TESTFG"))
    ok, err, update_status = mcd_model.update_fft_in_project(db, "editor_user", prjid,
                                                             {"_id": fftid, "tc_part_no": "PART 123"})
    assert err == ""
    assert ok
    assert update_status.success == 1

    # verify status and submitter (should not exist right now)
    project = mcd_model.get_project(db, prjid)
    assert project["status"] == "development"
    assert project.get("submitter", None) is None

    # the editor should be able to submit a project
    ok, err, project = mcd_model.submit_project_for_approval(db, prjid, "editor_user", project['editors'], ['approve_user'], notifier)
    assert err == ""
    assert ok
    assert project["_id"] == prjid
    assert project["status"] == "submitted"
    assert project["submitter"] == "editor_user"

    # verify notifications
    assert len(email_sender.emails_sent) == 2, "wrong number of notification emails sent"
    approver_email = email_sender.emails_sent[0]
    assert approver_email['to'] == ['approve_user', 'super_approver']
    assert approver_email['subject'] == "You were selected as an approver for the project test_approval_workflow"

    # this project was submitted for the first time, therefore an initial message should be sent to editors
    editor_email = email_sender.emails_sent[1]
    assert editor_email['to'] == ["editor_user", "editor_user_2", "test_user"]
    assert editor_email['subject'] == "Project test_approval_workflow was submitted for approval"
    email_sender.clear()

    project = mcd_model.get_project(db, prjid)
    assert project['approvers'] == ["approve_user", "super_approver"]
    assert project.get('approved_by', []) == []

    # TODO: once super_approver branch is merged in approve by super approver
    ok, all_approved, err, prj = mcd_model.approve_project(db, prjid, "super_approver", notifier)
    assert err == ""
    assert ok
    assert all_approved == False
    assert prj['approved_by'] == ['super_approver']
    assert len(email_sender.emails_sent) == 0, "there should be no notifications"
    assert prj['status'] == 'submitted'

    # approve by the final approver, we should receive notifications about approved project
    ok, all_approved, err, prj = mcd_model.approve_project(db, prjid, 'approve_user', notifier)
    assert err == ""
    assert ok
    assert all_approved, "the project should be approved"
    # approved this project goes back into a development branch
    assert prj['editors'] == []
    assert prj['approvers'] == []
    assert prj['approved_by'] == []
    assert prj['status'] == 'development'

    # the changed fft data should reflect in the master project
    master_project = mcd_model.get_master_project(db)
    ffts = mcd_model.get_fft_values_by_project(db, fftid, master_project['_id'])
    assert ffts['tc_part_no'] == "PART 123"

    assert len(email_sender.emails_sent) == 1, "only one set of messages should be sent"
    email = email_sender.emails_sent[0]
    assert email['to'] == ['approve_user', 'editor_user', 'editor_user_2', 'super_approver', 'test_user']
    assert email['subject'] == 'Project test_approval_workflow was approved'
    email_sender.clear()


def test_project_rejection(db):
    project = mcd_model.create_new_project(db, "test_project_rejection_workflow", "", "test_user")
    prjid = project["_id"]

    email_sender = TestEmailSender()
    notifier = Notifier('', email_sender, 'admin@example.com')
    ok, err = mcd_model.update_project_details(db, "test_user", prjid, {'editors': ['editor_user', 'editor_user_2']},
                                               notifier)
    assert err == ""
    assert ok

    ok, err, prj = mcd_model.submit_project_for_approval(db, prjid, "test_user", ['editor_user', 'editor_user_2'], ['approve_user', 'approve_user_2'], notifier)
    assert err == ""
    assert ok
    assert prj['status'] == "submitted"

    # clear sender so we can verify the rejection notifications
    email_sender.clear()

    # approve 1/2 approvers
    ok, all_approved, err, prj = mcd_model.approve_project(db, prjid, "approve_user", notifier)
    assert err == ""
    assert ok
    assert all_approved == False
    assert len(email_sender.emails_sent) == 0, "no emails should be sent"
    assert prj['approved_by'] == ['approve_user']

    # reject
    ok, err, prj = mcd_model.reject_project(db, prjid, "test_user", "This is my rejection message", notifier)
    assert err == ""
    assert ok
    assert prj['status'] == "development", "status should go back into a development state"
    assert prj['editors'] == ['editor_user', 'editor_user_2']
    assert prj['approvers'] == ['approve_user', 'approve_user_2', 'super_approver']

    # validate that notifications were send
    assert len(email_sender.emails_sent) == 1
    email = email_sender.emails_sent[0]
    assert email['to'] == ['approve_user', 'approve_user_2', 'editor_user', 'editor_user_2', 'super_approver', 'test_user']
    assert email['subject'] == 'Project test_project_rejection_workflow was rejected'
    assert 'This is my rejection message' in email['content']


def create_string_logger(stream: io.StringIO) -> logging.Logger:
    logger = logging.getLogger('str_logger')
    logger.setLevel(logging.DEBUG)
    for handler in logger.handlers[:]:
        # remove previous handlers, to avoid getting writing to a closed stream error during tests
        logger.removeHandler(handler)
    stream_handler = logging.StreamHandler(stream)
    stream_handler.setLevel(logging.DEBUG)
    logger.addHandler(stream_handler)
    return logger


def test_import_csv_into_a_project(db):
    project = mcd_model.create_new_project(db, "test_import_csv_into_a_project", "", "test_user")
    prjid = project["_id"]

    ffts = mcd_model.get_project_ffts(db, prjid)
    assert len(ffts) == 0, "There should be no project ffts for a freshly created project"

    # import via csv endpoint
    import_csv = """
Machine Config Database,,,

FC,Fungible,TC_part_no,Stand,State,Comments,LCLS_Z_loc,LCLS_X_loc,LCLS_Y_loc,LCLS_Z_roll,LCLS_X_pitch,LCLS_Y_yaw,Must_Ray_Trace
AT1L0,COMBO,12324,SOME_TEST_STAND,Conceptual,TEST,1.21,0.21,2.213,1.231,,,
AT1L0,GAS,3213221,,Conceptual,GAS ATTENUATOR,,,,1.23,-1.25,-0.895304,1
"""

    with io.StringIO() as stream:
        log_reporter = create_string_logger(stream)
        ok, err, counter = mcd_import.import_project(db, "test_user", prjid, import_csv, log_reporter)
        assert err == ""
        assert ok

        assert counter.success == 2
        assert counter.fail == 0
        assert counter.ignored == 0
        headers = "FC,Fungible,TC_part_no,Stand,State,Comments,LCLS_Z_loc,LCLS_X_loc,LCLS_Y_loc,LCLS_Z_roll,LCLS_X_pitch,LCLS_Y_yaw,Must_Ray_Trace"
        assert counter.headers == len(headers.split(",")), "wrong number of csv fields"

        log = stream.getvalue()
        # validate export log?

        # check if fields were actually inserted in the db
        ffts = mcd_model.get_project_ffts(db, prjid)
        assert len(ffts) == 2, "There should be 2 ffts inserted into a project"

        expected_ffts = {
            'COMBO': {'fc': 'AT1L0', 'fg': 'COMBO', 'tc_part_no': '12324', 'stand': 'SOME_TEST_STAND',
                      'state': 'Conceptual', 'comments': 'TEST',
                      'nom_loc_z': 1.21, 'nom_loc_x': 0.21, 'nom_loc_y': 2.213, 'nom_ang_z': 1.231},
            'GAS': {'fc': 'AT1L0', 'fg': 'GAS', 'tc_part_no': '3213221',
                    'state': 'Conceptual', 'comments': 'GAS ATTENUATOR',
                    'nom_ang_z': 1.23, 'nom_ang_x': -1.25, 'nom_ang_y': -0.895304, 'ray_trace': 1},
        }

        # convert received ffts into a format that we can compare (fgs are unique)
        got_ffts = {}
        for _, f in ffts.items():
            fc = f['fft']['fc']
            fg = f['fft']['fg']
            f['fc'] = fc
            f['fg'] = fg
            got_ffts[fg] = f

        # assert fft values
        for expected in expected_ffts.values():
            fg = expected['fg']
            assert fg in got_ffts, f"{expected['fg']} fg was not found in ffts: fft was not inserted correctly"
            got = got_ffts[fg]

            for field in mcd_model.KEYMAP.values():
                # empty fields are by default set to '' (not None) even if they are numeric fields. Is this okay?
                assert got.get(field, '') == expected.get(field, ''), f"{fg}: invalid field value '{field}'"

        assert len(got_ffts) == len(expected_ffts), "wrong number of fft fetched from db"


def test_export_csv_from_a_project(db):
    project = mcd_model.create_new_project(db, "test_export_from_a_project", "", "test_user")
    prjid = project["_id"]

    ffts = mcd_model.get_project_ffts(db, prjid)
    assert len(ffts) == 0, "There should be no project ffts for a freshly created project"

    # import via csv endpoint
    import_csv = """
FC,Fungible,TC_part_no,Stand,State,Comments,LCLS_Z_loc,LCLS_X_loc,LCLS_Y_loc,LCLS_Z_roll,LCLS_X_pitch,LCLS_Y_yaw,Must_Ray_Trace
AT1L0,COMBO,12324,SOME_TEST_STAND,Conceptual,TEST,1.21,0.21,2.213,1.231,,,
AT1L0,GAS,3213221,,Conceptual,GAS ATTENUATOR,,,,1.23,-1.25,-0.895304,1
"""

    with io.StringIO() as stream:
        log_reporter = create_string_logger(stream)
        ok, err, counter = mcd_import.import_project(db, "test_user", prjid, import_csv, log_reporter)
        assert err == ""
        assert ok
        assert counter.success == 2

    ok, err, csv = mcd_import.export_project(db, prjid)
    assert ok
    assert err == ""
    # by default the csv writer ends the lines with \r\n, so this assert would fail without our replace
    csv = csv.replace("\r\n", "\n")
    assert import_csv.strip() == csv.strip(), "wrong csv output"