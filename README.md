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
2. After the hosts have booted, upgrade them to Ubuntu 21.10. This is pretty much just running `sudo do-release-upgrade` on the hosts. Ubuntu 21.10 is required to avoid certain kernel panics when using SoftRoCE.
3. Change the two hostnames of the `no_mlnx_ofed` group to your Cloudlab hostnames in `ansible/hosts.yaml`.
4. Run `ansible-playbook --ssh-common-args "-o StrictHostKeyChecking=no" --inventory-file="./hosts.yaml" --limit no_mlnx_ofed site.yml` while in the `ansible` directory.
5. Run the commands listed in `data/softroce_*/metadata*` while in the `test_scripts` directory. Take care to replace the `--host1` and `--host2` flags to match your Cloudlab hostnames, and `--user` to match your Cloudlab username. The first argument (`/opt/homebrew/.../Python`) should be replaced with the path to your Python 3.10 binary. 
    * Run the host (i.e. non-SoftRoCE) versions of the test first.
    * Then, for running the SoftRoCE version of `run_basic_tests` and `run_cpu_tests`, a SoftRoCE NIC must be manually configured before running the tests. SSH into both hosts and run `sudo modprobe -rv mlx5_ib && sudo reboot now`. After they reboot, run `sudo rdma link | grep rxe0 || sudo rdma link add rxe0 type rxe netdev enp65s0f0np0 && sudo devlink dev param set pci/0000:41:00.0 name enable_roce value false cmode driverinit && sudo devlink dev reload pci/0000:41:00.0`. Then run the test commands.
6. The data should appear in `data/raw`. You can generate graphs based on the data you just produced by rerunning all cells in the `SoftRoCE*.ipynb` Jupyter notebooks (run `jupyter-notebook` while in the `data` dir).
