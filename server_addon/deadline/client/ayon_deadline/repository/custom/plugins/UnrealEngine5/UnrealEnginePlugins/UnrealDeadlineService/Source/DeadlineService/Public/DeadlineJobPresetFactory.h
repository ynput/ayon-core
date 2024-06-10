// Copyright Epic Games, Inc. All Rights Reserved.
#pragma once

#include "Factories/Factory.h"

#include "DeadlineJobPresetFactory.generated.h"

UCLASS()
class UDeadlineJobPresetFactory : public UFactory
{
	GENERATED_BODY()

public:

	UDeadlineJobPresetFactory();
	
	// Begin UFactory Interface
	virtual UObject* FactoryCreateNew(UClass* Class, UObject* InParent, FName Name, EObjectFlags Flags, UObject* Context, FFeedbackContext* Warn) override;
	virtual FText GetDisplayName() const override;
	virtual uint32 GetMenuCategories() const override;
	// End UFactory Interface
};

