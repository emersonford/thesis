docker run --name router1 --ulimit memlock=-1:-1 --shm-size=8g --net host -e "HOST_IP={{ host_ip_addr }}" -e "FFR_NAME=router1" -e "LD_LIBRARY_PATH=/usr/lib/:/usr/local/lib/:/usr/lib64/" --ipc=shareable -v /freeflow:/freeflow --privileged -it -d ffrouter
docker run --name node1 --ulimit memlock=-1:-1 --shm-size=8g --net host -e "FFR_NAME=router1" -e "FFR_ID=10" -e "LD_LIBRARY_PATH=/usr/lib" --ipc=container:router1 -v /freeflow:/freeflow --privileged -it -d ffclient
