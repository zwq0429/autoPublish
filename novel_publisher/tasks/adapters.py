"""任务适配器：将现有的 scheduled_* 方法桥接到任务注册表。"""

from . import register_task


@register_task("本地定时发布")
def scheduled_publish(app):
    app.scheduled_publish()


@register_task("自动签约")
def scheduled_sign(app):
    app.scheduled_sign()


@register_task("自动验证")
def scheduled_verify(app):
    app.scheduled_verify()


@register_task("短故事发布", threaded=False)
def publish_sstory(app):
    app.publish_sstory()


@register_task("短故事批量发布")
def scheduled_publish_story_batch(app):
    app.scheduled_publish_story_batch()


@register_task("书测")
def schedule_command_by_name(app):
    app.schedule_command_by_name()


@register_task("封测")
def schedule_command_by_cover(app):
    app.schedule_command_by_cover()


@register_task("全勤检查")
def schedule_check_attendance(app):
    app.schedule_check_attendance()


@register_task("发布进度自检")
def process_check(app):
    app.process_check()


@register_task("取消定时")
def cancel_scheduled_task(app):
    app.cancel_scheduled_task()


@register_task("快速创书")
def create_book_from_outline(app):
    app.create_book_from_outline()
