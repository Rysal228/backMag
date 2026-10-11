from django.db import migrations, models

import chats.storage


class Migration(migrations.Migration):
    dependencies = [
        ('chats', '0002_chatattachment_message_text_blank'),
    ]

    operations = [
        migrations.AlterField(
            model_name='chatattachment',
            name='file',
            field=models.FileField(
                storage=chats.storage.PrivateChatAttachmentStorage(),
                upload_to='chat_attachments/%Y/%m/',
            ),
        ),
    ]
