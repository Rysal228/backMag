from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0028_order_refusal_reason"),
        ("cars", "0007_native_owner_uuid"),
    ]

    operations = [
        # Requires an explicitly cleared set of test orders (see deployment docs).
        migrations.RemoveField(model_name="order", name="mechanics"),
        migrations.RemoveField(model_name="order", name="customer"),
        migrations.AddField(
            model_name="order", name="customer_id",
            field=models.UUIDField(db_index=True),
        ),
        migrations.AddField(
            model_name="order", name="customer_phone_snapshot",
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AddField(
            model_name="order", name="customer_name_snapshot",
            field=models.CharField(blank=True, max_length=450),
        ),
        migrations.CreateModel(
            name="OrderMechanic",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("mechanic_id", models.UUIDField(db_index=True)),
                ("order", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="mechanic_links", to="orders.order",
                )),
            ],
        ),
        migrations.AddConstraint(
            model_name="ordermechanic",
            constraint=models.UniqueConstraint(
                fields=("order", "mechanic_id"),
                name="unique_order_native_mechanic",
            ),
        ),
        migrations.AddIndex(
            model_name="ordermechanic",
            index=models.Index(
                fields=["mechanic_id", "order"],
                name="order_mechanic_native_idx",
            ),
        ),
    ]
