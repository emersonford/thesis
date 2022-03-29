# Explaining and Evaluating the Use of RDMA in High Performance Containers
Honors Computer Science Bachelor's Thesis by Emerson Ford at the University of Utah.

## Folders
1. `ansible` an ansible playbook to setup hosts for testing various RDMA-in-container solutions.
2. `bg_presentation` background presentation on the topic of this thesis
3. `data` raw data gathered for each RDMA-in-container solution test
4. `Freeflow` submodule to a fork of Freeflow, which required a few alterations to get working and includes some QoL changes to make testing faster
5. `paper` actual document in LaTeX for this thesis

## Reproducing Data
This assumes you're using [Cloudlab](https://www.cloudlab.us/) and have SSH keys configured on your Cloudlab account. You should also have `ansible-playbook` and Python 3.10 installed.

### SoftRoCE Tests
1. Provision a Cloudlab experiment with the [roce-cluster](https://www.cloudlab.us/show-profile.php?uuid=fbcf91c3-93ba-11ec-9467-e4434b2381fc) profile.
    * Change "Node type to use" to `d6515`.
2. After the hosts have booted, upgrade them to Ubuntu 21.10. This is pretty much just running `sudo do-release-upgrade` on the hosts. 
3. Change the two hostnames of the `no_mlnx_ofed` group to your Cloudlab hostnames in `ansible/hosts.yaml`. Change `ansible_user` under `vars` to your Cloudlab username.
4. Run `ansible-playbook --ssh-common-args "-o StrictHostKeyChecking=no" --inventory-file="./hosts.yaml" --limit no_mlnx_ofed site.yml` while in the `ansible` directory.
5. Run the commands listed in `data/softroce_*/metadata*` while in the `test_scripts` directory. Take care to replace the `--host1` and `--host2` flags to match your Cloudlab hostnames, and `--user` to match your Cloudlab username. The first argument (`/opt/homebrew/.../Python`) should be replaced with the path to your Python 3.10 binary. 
    * Run the host (i.e. non-SoftRoCE) versions of the test first.
    * Then, for running the SoftRoCE version of `run_basic_tests` and `run_cpu_tests`, a SoftRoCE NIC must be manually configured before running the tests. SSH into both hosts and run `sudo modprobe -rv mlx5_ib && sudo reboot now`. After they reboot, run `sudo rdma link | grep rxe0 || sudo rdma link add rxe0 type rxe netdev enp65s0f0np0 && sudo devlink dev param set pci/0000:41:00.0 name enable_roce value false cmode driverinit && sudo devlink dev reload pci/0000:41:00.0`. Then run the test commands.
6. The data should appear in `data/raw`. You can generate graphs based on the data you just produced by setting `MODE = "softroce"` and rerunning all cells in the `*.ipynb` Jupyter notebooks (run `jupyter-notebook` while in the `data` dir).

#### Quirks to Watch Out For
1. Ubuntu 21.10 / Linux Kernel >5.13 is required to avoid certain kernel panics when using SoftRoCE.

### Shared HCA Tests
1. Provision a Cloudlab experiment with the [roce-cluster](https://www.cloudlab.us/show-profile.php?uuid=fbcf91c3-93ba-11ec-9467-e4434b2381fc) profile.
    * Change "Node type to use" to `c6526-100g`.
2. Change the two hostnames of the `connectx5` group to your Cloudlab hostnames in `ansible/hosts.yaml`. Change `ansible_user` under `vars:` to your Cloudlab username.
3. Run `ansible-playbook --ssh-common-args "-o StrictHostKeyChecking=no" --inventory-file="./hosts.yaml" --limit connectx5 site.yml` while in the `ansible` directory. Reboot both hosts after the "Wait for mlnxofedinstall" handler. Rerun the `ansible-playbook` command to completion.
4. Run the commands listed in `data/shared_hca_*/metadata*` while in the `test_scripts` directory. Take care to replace the `--host1` and `--host2` flags to match your Cloudlab hostnames, and `--user` to match your Cloudlab username. The first argument (`/opt/homebrew/.../Python`) should be replaced with the path to your Python 3.10 binary. 
    * For running the Shared HCA version of `run_basic_tests` and `run_cpu_tests`, a Docker macvlan network must first be created with `docker network ls | grep mynet || docker network create -d macvlan --subnet=192.168.1.0/24 -o parent=ens1f0 -o macvlan_mode=private mynet`.
6. The data should appear in `data/raw`. You can generate graphs based on the data you just produced by setting `MODE = "shared_hca"` and rerunning all cells in the `*.ipynb` Jupyter notebooks (run `jupyter-notebook` while in the `data` dir).

#### Quirks to Watch Out For
1. The RDMA GID table is namespaced inside of the container, thus the majority of GID entries are `0000:0000:0000:0000:0000:0000:0000:0000`, and the ones namespaced into the container's namespace are populated. Despite this, `ib_[read|write|send]_[bw|lat]` do not select the proper GID and will error with `Failed to modify QP XXXX to RTR` and `Unable to Connect the HCA's through the link`. You can force `ib_[read|write|send]_[bw|lat]` to use the correct GID entry with the `-x` flag. See `/sys/class/infiniband/*/ports/*/gids` for GID entry values and `/sys/class/infiniband/*/ports/*/gid_attrs/types` for the corresponding type (RoCE v1, RoCE v2, etc).
    * You can use `rdma_cm` queue pairs to avoid this with the `-R` flag. However, using RDMA connection manager queue pairs results in 100% CPU utilization on the `ib_[read|write|send]_[bw|lat]` server (which should have around a 0% CPU util for read/write operations), thus their use can result in incorrect CPU usage readings.
