variable "az_1" {
    type = string
}

variable "az_2" {
    type = string
}

variable "private_subnet_ids" {
    type = list(string)
}

variable "rds_password" {
    type = string
}

variable "elasticache_password" {
    type = string
}

variable "rds_sg_id" {
    type = string
}