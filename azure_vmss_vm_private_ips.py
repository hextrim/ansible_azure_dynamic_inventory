#!/usr/bin/env python
import os
import re
import pprint
import argparse
from jinja2 import Environment, FileSystemLoader
from azure.common.credentials import ServicePrincipalCredentials
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.resource import ResourceManagementClient, SubscriptionClient
from azure.mgmt.network import NetworkManagementClient

# Parser
parser = argparse.ArgumentParser()
parser.add_argument('-rg', dest='rg', action='store', help="[i] Requires -rg Azure Resource Group")
args = parser.parse_args()

# Tenant ID for your Azure Subscription
ARM_TENANT_ID = os.environ.get('ARM_TENANT_ID', 'None')

# Your Service Principal App ID
ARM_CLIENT_ID = os.environ.get('ARM_CLIENT_ID', 'None')

# Your Service Principal Password
ARM_CLIENT_SECRET = os.environ.get('ARM_CLIENT_SECRET', 'None')

# Your Azure Subscription ID
ARM_SUBSRIPTION_ID = os.environ.get('ARM_SUBSCRIPTION_ID','None')

# Your Resource Group where from you want to build inventory file
rg = args.rg.lower()
#rg = os.environ.get('ARM_RESOURCE_GROUP', 'None')

# Jinja2 variables
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
TEMPLATE_DIR = '.'
TEMPLATE_CONFIG = os.path.join(BASE_DIR, TEMPLATE_DIR)

template_file = 'azure_vpc_inventory.j2'
template_output = 'inventory/' + rg + '/inventory_hosts'

# LOCAL VARIABLES
vmss_dict = {'amq_vmss':    { 'ids': [] },
             'consul_vmss': { 'ids': [] },
             'app_vmss': { 'ids': [] },
             'gluster_vmss': { 'ids': [] },
             'haproxy_vmss': { 'ids': [] },
             'mongo_vmss': { 'ids': [] }
            }

# Register AzureRM call
CREDENTIALS = ServicePrincipalCredentials(
    client_id = ARM_CLIENT_ID,
    secret = ARM_CLIENT_SECRET,
    tenant = ARM_TENANT_ID
)

compute_client = ComputeManagementClient(CREDENTIALS, ARM_SUBSRIPTION_ID)
network_client = NetworkManagementClient(credentials=CREDENTIALS, subscription_id=ARM_SUBSRIPTION_ID)

# Lookup and Inventory Build

def get_vm_private_ip(compute_client, network_client):
    global bastion_vm
    global consul_vm
    for vm in compute_client.virtual_machines.list(rg):
        print("[VM] VM_NAME: ", vm.name)
        for interface in vm.network_profile.network_interfaces:
            name=" ".join(interface.id.split('/')[-1:])
            subnet="".join(interface.id.split('/')[4])
            net_int=network_client.network_interfaces.get(subnet, name).ip_configurations
            for int in net_int:
                print("[VM] VM_PRIVATE_IP: ", int.private_ip_address)
            if re.search("^bastion-.*$", str(vm.name)):
                bastion_vm = dict({"vm_name": vm.name, "vm_private_ip":
                               int.private_ip_address })
            if re.search("^consul-.*$", str(vm.name)):
                consul_vm = dict({"vm_name": vm.name, "vm_private_ip":
                               int.private_ip_address })

get_vm_private_ip(compute_client, network_client)

def get_vmss_vm_private_ip(compute_client):
    global vmss_dict
    for vmss in compute_client.virtual_machine_scale_sets.list(rg):
        print("[VMSS] VM_SCALE_SET_NAME: ", vmss.name)
        for vmssvm in compute_client.virtual_machine_scale_set_vms.list(rg,vmss.name):
            print("[VMSS] VM_SCALE_SET_VM_NAME: ", vmssvm.name)
            ni_reference = vmssvm.network_profile.network_interfaces[0].id
            resource_client = ResourceManagementClient(credentials=CREDENTIALS, subscription_id=ARM_SUBSRIPTION_ID)
            nic = resource_client.resources.get_by_id(ni_reference, api_version='2017-12-01')
            ip_reference = nic.properties['ipConfigurations'][0]['properties']['privateIPAddress']
            print("[VMSS] VM_SCALE_SET_VM_PRIVATE_IP: ", ip_reference)
            if re.search("^ACTIVEMQ-", vmss.name):
                vmss_dict['amq_vmss']['ids'].append({ 'vm_name': vmssvm.name, 'vm_private_ip': ip_reference })
            if re.search("^CONSUL-", vmss.name):
                vmss_dict['consul_vmss']['ids'].append({'vm_name': vmssvm.name, 'vm_private_ip': ip_reference })
            if re.search("^APP-", vmss.name):
                vmss_dict['app_vmss']['ids'].append({ 'vm_name': vmssvm.name, 'vm_private_ip': ip_reference })
            if re.search("^GLUSTER-", vmss.name):
                vmss_dict['gluster_vmss']['ids'].append({'vm_name': vmssvm.name, 'vm_private_ip': ip_reference })
            if re.search("^HAPROXY-", vmss.name):
                vmss_dict['haproxy_vmss']['ids'].append({ 'vm_name': vmssvm.name, 'vm_private_ip': ip_reference })
            if re.search("^MONGO-", vmss.name):
                vmss_dict['mongo_vmss']['ids'].append({'vm_name': vmssvm.name, 'vm_private_ip': ip_reference })

get_vmss_vm_private_ip(compute_client)

pprint.pprint(vmss_dict)

env = Environment(loader=FileSystemLoader(TEMPLATE_CONFIG))
template = env.get_template(template_file)
generate_template = template.render(rg=rg, bastion_vm=bastion_vm, consul_vm=consul_vm,
                                   vmss_dict=vmss_dict)
with open(template_output, "wb") as f:
    f.write(generate_template)
