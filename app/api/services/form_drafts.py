from app.models.model import Form, FormConsent, Page, Project, ProjectStakeholder


DEFAULT_CONSENT = {
    "title": "USR計畫參與同意書與資料授權書",
    "organization_name": "政治大學「多元共容・文山共好」USR計畫團隊",
    "content": (
        "您好，我們需要您參與本問卷調查之資料，作為檔案紀錄，並授權給計畫辦公室與計畫主持人"
        "製作計畫成果報告書，以及作為教育目的之簡報與研究成果。參與完全出於自願，您可以選擇不參與。"
    ),
    "secondary_use_description": (
        "若有非本計畫之老師、助理或學生欲將本課程、活動或工作坊所產生的資料作為教學或研究使用，"
        "計畫辦公室將審核其研究計畫，僅在能保護個人隱私並與計畫維持互惠關係時提供去識別化資料。"
    ),
    "withdrawal_method": "如欲撤回同意，請透過下方聯絡方式與計畫辦公室聯繫。",
    "contact_name": "政大「多元共容・文山共好」USR計畫辦公室",
    "contact_email": "nccuusr@gmail.com",
    "contact_phone": "02-29393091 分機 51479",
    "requires_guardian": True,
    "secondary_use_enabled": True,
}


RESPONDENT_INFO_CONTENT = "請填寫以下基本資料，電子郵件將用於確認每人只填寫一次。"


def new_form_consent() -> FormConsent:
    return FormConsent(version=0, is_published=False, **DEFAULT_CONSENT)


def add_stakeholder_form(project: Project, stakeholder: ProjectStakeholder, author_id: str) -> None:
    form = Form(stakeholder_id=stakeholder.stakeholder_id, author_id=author_id,
                title=f"{stakeholder.name[:250]}｜成果問卷", content="")
    form.consent_versions.append(new_form_consent())
    form.pages.append(Page(
        is_respondent_info=True, title="基本資料", content=RESPONDENT_INFO_CONTENT, position=0,
    ))
    for position, outcome in enumerate((item for item in stakeholder.outcomes if not item.is_delete), 1):
        form.pages.append(Page(
            project_outcome_id=outcome.outcome_id, title=outcome.name, content="", position=position,
        ))
    project.forms.append(form)
    if stakeholder.post_form_id is None:
        stakeholder.post_form = form
