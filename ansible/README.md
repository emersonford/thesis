# RDMA in High Performance Containers Ansible Playbook

I recommend using the "roce-cluster" Cloudlab profile: https://www.cloudlab.us/show-profile.php?uuid=2954466f-68e4-11ec-9467-e4434b2381fc

Then input the host names from the provisioned experiment to `hosts.yml`. Also change `ansible_user` in `hosts.yaml` to your Cloudlab unix name.

You can then run the playbook with a command like `ansible-playbook --ssh-common-args "-o StrictHostKeyChecking=no" --inventory-file="./hosts.yaml" --limit connectx5 site.yml`.

## RDMA Drivers and Libraries
There are two different RDMA driver / library distributions: MLNX\_OFED and `rdma-core`. Only one of these should be installed at any time on a host.

1. MLNX\_OFED provides Mellanox specific libraries and drivers.
2. `rdma-core` is a generic RDMA/Infiniband library and driver distribution. Use of SoftRoCE requires using this distribution and _not_ MLNX\_OFED.

To uninstall MLNX\_OFED, run `~root/MLNX_OFED.../uninstall.sh` if you installed it using the `mellanox` role.

Install/uninstall `rdma-core` using `apt`.

## Roles
1. `docker` installs packages to run Docker containers and builds two Docker containers, one with the generic RDMA stack and one with the Mellanox RDMA stack.
2. `mellanox` installs MLNX\_OFED, Mellanox's RDMA/Infiniband driver and library distribution. 
3. `freeflow` clones and builds Freeflow. Currently, Freeflow only works with CX3 NICs. Freeflow containers can be started with `~{{ ansible_user }}/Freeflow/start_containers.sh`.
4. `connectx3` configures RoCE on CX3 NICs.
5. `cpufreq` disables CPU idle states and sets CPU frequency to max. This eliminates CPU frequency errors from `ib_[read][write][send]_[lat][bw]` and ensures accurate timing results.
6. `sysstat` installs `mpstat` and `sar` to measure CPU utilization.
