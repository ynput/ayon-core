// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "IPropertyTypeCustomization.h"

class IDetailPropertyRow;
class UMoviePipelineDeadlineExecutorJob;

/**
 * This customization lives in the MoviePipelineDeadline module because in order to get
 * the preset assigned to the owning job, we need to cast the owning object to the
 * UMoviePipelineDeadlineExecutorJob class. We need the assigned preset for the custom
 * ResetToDefault behaviour.
 */
class FDeadlineJobPresetCustomization : public IPropertyTypeCustomization
{
public:

	static TSharedRef< IPropertyTypeCustomization > MakeInstance();

	/** Begin IPropertyTypeCustomization interface */
	virtual void CustomizeHeader(TSharedRef<IPropertyHandle> PropertyHandle, FDetailWidgetRow& HeaderRow, IPropertyTypeCustomizationUtils& CustomizationUtils) override {}
	virtual void CustomizeChildren(TSharedRef<IPropertyHandle> StructHandle, IDetailChildrenBuilder& ChildBuilder, IPropertyTypeCustomizationUtils& CustomizationUtils) override;
	/** End IPropertyTypeCustomization interface */

	static bool IsPropertyHiddenInMovieRenderQueue(const FName& InPropertyPath);
	static bool IsPropertyRowEnabledInMovieRenderJob(const FName& InPropertyPath, UMoviePipelineDeadlineExecutorJob* Job);
	
protected:
	void CustomizeStructChildrenInAssetDetails(IDetailPropertyRow& PropertyRow) const;
	void CustomizeStructChildrenInMovieRenderQueue(IDetailPropertyRow& PropertyRow, UMoviePipelineDeadlineExecutorJob* Job) const;

	static bool IsResetToDefaultVisibleOverride(TSharedPtr<IPropertyHandle> PropertyHandle, UMoviePipelineDeadlineExecutorJob* Job);
	static void ResetToDefaultOverride(TSharedPtr<IPropertyHandle> PropertyHandle, UMoviePipelineDeadlineExecutorJob* Job);
};
