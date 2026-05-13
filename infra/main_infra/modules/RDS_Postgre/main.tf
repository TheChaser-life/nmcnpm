resource "aws_db_subnet_group" "db_private_subnet_group" {
    name = "db_private_subnet_group"

    subnet_ids = var.private_subnet_ids
}

resource "aws_db_instance" "rds_postgres_primary" {
    identifier = "rds-postgres-primary"
    engine = "postgres"
    instance_class = "db.t3.micro"
    allocated_storage = 20

    username = "postgres"
    password = var.rds_password

    db_subnet_group_name   = aws_db_subnet_group.db_private_subnet_group.name
    vpc_security_group_ids = [var.rds_sg_id]

    availability_zone = var.az_1

    backup_retention_period = 7

    multi_az = false

    skip_final_snapshot = true
}

resource "aws_db_instance" "rds_postgres_read_replica" {
    identifier = "rds-postgres-read-replica"
    replicate_source_db = aws_db_instance.rds_postgres_primary.identifier
    instance_class = "db.t3.micro"

    availability_zone = var.az_2

    skip_final_snapshot = true
}