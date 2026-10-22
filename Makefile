.PHONY: test validate image clean

test:
	python3 -m unittest discover -s tests -v

validate: test
	python3 -m allieos.cli list

image:
	sudo bash ./scripts/build-image.sh

clean:
	cd build/live && lb clean --purge
